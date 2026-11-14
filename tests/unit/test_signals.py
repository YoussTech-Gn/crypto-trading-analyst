"""Milestone 4 tests: signal decision rules, persistence, API."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from database.migrations.runner import apply_migrations
from database.session import create_connection
from packages.config.settings import SignalConfig, load_config
from packages.signals import SignalGenerator, SignalRepository

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
H4 = 4 * 3_600_000


def base_analysis(**over):
    """Last index 99. Sweep at 97 (low 100), FVG [104,106] formed at 98, swing high 120, close 105."""
    a = {
        "symbol": "TESTUSDT", "version": "analysis-1.0",
        "setup_last_open_time_ms": 99 * H4, "setup_candle_count": 100,
        "indicators": {"setup_last_close": 105.0, "setup_atr": 2.0},
        "daily_trend": {"bullish": True, "failed_conditions": [], "evidence": {}},
        "sweep_events": [{"sweep_index": 97, "sweep_low": 100.0, "levels": [], "deepest_penetration_pct": 0.5}],
        "fair_value_gaps": [{"index": 98, "lower": 104.0, "upper": 106.0, "status": "UNTOUCHED", "formed_time_ms": 1}],
        "setup_swings": [{"kind": "HIGH", "price": 120.0}, {"kind": "LOW", "price": 90.0}],
    }
    a.update(over)
    return a


GEN = SignalGenerator(SignalConfig(), 2.0)


def test_full_setup_gives_signal_with_correct_levels():
    d = GEN.decide(base_analysis())
    assert d.decision == "SIGNAL" and d.reasons == ()
    assert d.entry == 105.0 and d.stop == pytest.approx(100.0 - 0.25 * 2.0) and d.target == 120.0
    assert d.risk_reward == pytest.approx((120 - 105) / (105 - 99.5))
    assert d.valid_until_ms == 99 * H4 + H4 + 6 * H4 and d.paper_only


def test_each_failed_check_blocks_and_is_named():
    cases = {
        "DAILY_TREND_BULLISH": base_analysis(daily_trend={"bullish": False, "failed_conditions": ["X"], "evidence": {}}),
        "RECENT_SELL_SIDE_SWEEP": base_analysis(sweep_events=[]),
        "OPEN_FVG_AFTER_SWEEP": base_analysis(fair_value_gaps=[{"index": 98, "lower": 104.0, "upper": 106.0, "status": "FILLED", "formed_time_ms": 1}]),
        "ATR_AVAILABLE": base_analysis(indicators={"setup_last_close": 105.0, "setup_atr": None}),
        "PRICE_NEAR_ENTRY": base_analysis(indicators={"setup_last_close": 109.0, "setup_atr": 2.0}),
        "TARGET_AVAILABLE": base_analysis(setup_swings=[{"kind": "HIGH", "price": 100.0}]),
        "REWARD_TO_RISK_OK": base_analysis(setup_swings=[{"kind": "HIGH", "price": 110.0}]),
        "PRICE_ABOVE_STOP": base_analysis(indicators={"setup_last_close": 99.0, "setup_atr": 2.0}),
    }
    for reason, a in cases.items():
        d = GEN.decide(a)
        assert d.decision == "NO_TRADE", reason
        assert reason in d.reasons, (reason, d.reasons)
        assert d.entry is None and d.stop is None and d.target is None


def test_old_sweep_outside_window_is_ignored():
    a = base_analysis(sweep_events=[{"sweep_index": 90, "sweep_low": 100.0, "levels": [], "deepest_penetration_pct": 0.5}])
    assert "RECENT_SELL_SIDE_SWEEP" in GEN.decide(a).reasons


def test_fvg_before_sweep_is_ignored():
    a = base_analysis(fair_value_gaps=[{"index": 95, "lower": 104.0, "upper": 106.0, "status": "UNTOUCHED", "formed_time_ms": 1}])
    assert "OPEN_FVG_AFTER_SWEEP" in GEN.decide(a).reasons


def test_decision_is_deterministic_and_id_stable():
    a = base_analysis()
    assert GEN.decide(a) == GEN.decide(a)
    assert GEN.decide(a).signal_id == GEN.decide(base_analysis()).signal_id


def test_no_data_is_no_trade_with_reason():
    d = GEN.no_data("XUSDT", 0, "4h:STALE")
    assert d.decision == "NO_TRADE" and d.reasons == ("DATA_INVALID:4h:STALE",)


def test_downtrend_only_reports_root_causes():
    a = base_analysis(daily_trend={"bullish": False, "failed_conditions": [], "evidence": {}}, sweep_events=[])
    d = GEN.decide(a)
    assert set(d.reasons) == {"DAILY_TREND_BULLISH", "RECENT_SELL_SIDE_SWEEP"}


# ---------------- persistence + API ----------------
@pytest.fixture()
def repo():
    conn = create_connection("sqlite:///:memory:")
    apply_migrations(conn)
    yield conn, SignalRepository(conn)
    conn.close()


def test_save_is_idempotent_and_roundtrips(repo):
    conn, r = repo
    d = GEN.decide(base_analysis())
    assert r.save(d, NOW) is True and r.save(d, NOW) is False
    rows = r.list_recent()
    assert len(rows) == 1 and rows[0]["decision"] == "SIGNAL" and rows[0]["reasons"] == []
    assert rows[0]["checks"]["DAILY_TREND_BULLISH"] is True
    nt = GEN.decide(base_analysis(sweep_events=[]))
    nt = nt.__class__(**{**nt.__dict__, "symbol": "OTHERUSDT", "signal_id": "x" * 32})
    r.save(nt, NOW)
    assert [x["symbol"] for x in r.list_recent("NO_TRADE")] == ["OTHERUSDT"]


def test_database_rejects_invalid_signal_levels(repo):
    conn, _ = repo
    with pytest.raises(Exception):
        conn.execute(
            """INSERT INTO signal_decisions (signal_id, symbol, decision, created_at_utc, setup_candle_open_time_ms,
               signal_version, entry_price, stop_price, target_price, checks_json, evidence_json, params_json)
               VALUES ('a','X','SIGNAL','t',1,'v',100,110,120,'{}','{}','{}')"""
        )


def test_database_rejects_signal_without_levels(repo):
    conn, _ = repo
    with pytest.raises(Exception):
        conn.execute(
            """INSERT INTO signal_decisions (signal_id, symbol, decision, created_at_utc, setup_candle_open_time_ms,
               signal_version, checks_json, evidence_json, params_json)
               VALUES ('b','X','SIGNAL','t',1,'v','{}','{}','{}')"""
        )


def test_api_signals_endpoint(tmp_path):
    from pathlib import Path
    cfg = load_config(Path(__file__).resolve().parents[2] / "config" / "default.yaml",
                      overrides={"database_url": "sqlite:///:memory:"})
    app = create_app(cfg)
    client = TestClient(app)
    assert client.get("/api/v1/signals").json()["count"] == 0
    conn = app.state.db_conn
    SignalRepository(conn).save(GEN.decide(base_analysis()), NOW)
    body = client.get("/api/v1/signals?decision=SIGNAL").json()
    assert body["count"] == 1 and body["decisions"][0]["symbol"] == "TESTUSDT"
    assert client.get("/api/v1/signals?decision=BUY").status_code == 422


def test_target_mode_first_meeting_rr_skips_too_close_highs():
    # entry 105, stop 99.5 (risk 5.5). nearest high 110 gives RR 0.9 (fails), 120 gives 2.7 (meets 2.0)
    a = base_analysis(setup_swings=[{"kind": "HIGH", "price": 110.0}, {"kind": "HIGH", "price": 120.0}])
    nearest = SignalGenerator(SignalConfig(), 2.0).decide(a)
    assert nearest.decision == "NO_TRADE" and "REWARD_TO_RISK_OK" in nearest.reasons
    far = SignalGenerator(SignalConfig(target_mode="first_meeting_rr"), 2.0).decide(a)
    assert far.decision == "SIGNAL" and far.target == 120.0 and far.risk_reward >= 2.0
    none = SignalGenerator(SignalConfig(target_mode="first_meeting_rr"), 2.0).decide(
        base_analysis(setup_swings=[{"kind": "HIGH", "price": 110.0}]))
    assert none.decision == "NO_TRADE" and "TARGET_AVAILABLE" in none.reasons


def test_invalid_target_mode_rejected():
    with pytest.raises(Exception):
        SignalConfig(target_mode="anything")
