"""Post-mortem, lessons (out-of-sample confirmation), optional vetoes, failure reports."""
from __future__ import annotations

import pytest

from packages.backtest.engine import Trade
from packages.backtest.postmortem import analyze_trade, build_postmortem, entry_flags, learn_lessons
from packages.config.settings import SignalConfig
from packages.reporting import failure
from packages.reporting.failure import classify_message, run_guarded
from packages.signals import SignalGenerator
from tests.unit.test_signals import base_analysis  # noqa: E402


def tr(r, reason="STOP", i=0, mae=0.3, mfe=0.5, bars=5, ctx=None):
    return Trade("A", i, i, 100, 95, 110, 2.0, i, i, i + bars, i + bars, 100, reason, r, bars, "", mae, mfe, ctx or {})


# ---------------- per-trade classification ----------------
def test_normal_stop_is_an_expected_rational_loss():
    a = analyze_trade(tr(-1.1))
    assert a["outcome"] == "LOSS" and a["category"] == "NORMAL_STOP" and a["expected"] is True


def test_gap_through_stop_is_unexpected():
    a = analyze_trade(tr(-2.4))
    assert a["category"] == "GAP_THROUGH_STOP" and a["expected"] is False


def test_timeout_loss_and_fast_failure_and_near_miss_notes():
    assert analyze_trade(tr(-0.3, "TIMEOUT"))["category"] == "TIMEOUT_LOSS"
    a = analyze_trade(tr(-1.1, bars=1, mfe=1.8))
    assert len(a["notes"]) == 2


def test_win_quality_lucky_clean_timeout():
    assert analyze_trade(tr(2.0, "TARGET", mae=0.9))["category"] == "LUCKY_WIN"
    assert analyze_trade(tr(2.0, "TARGET", mae=0.2))["category"] == "CLEAN_WIN"
    assert analyze_trade(tr(0.3, "TIMEOUT", mae=0.2))["category"] == "TIMEOUT_WIN"


def test_entry_flags_are_detected_from_context():
    t = tr(-1.0, ctx={"risk_atr": 0.6, "planned_rr": 2.2, "sweep_penetration_pct": 1.5, "fvg_size_atr": 0.1, "rsi": 70, "rel_volume": 0.5})
    assert set(entry_flags(t)) == {"TIGHT_STOP", "THIN_RR", "DEEP_SWEEP", "TINY_FVG", "HOT_RSI", "LOW_VOLUME"}
    assert entry_flags(tr(1.0, ctx={"risk_atr": 2.0, "planned_rr": 3.0})) == []


def test_postmortem_counts():
    ts = [tr(-1.0, i=1), tr(-3.0, i=2), tr(2.0, "TARGET", i=3, mae=0.9)]
    pm = build_postmortem(ts)
    assert pm["losses"] == 2 and pm["expected_losses"] == 1 and pm["unexpected_losses"] == 1 and pm["lucky_wins"] == 1


# ---------------- lessons need out-of-sample confirmation ----------------
def series(pattern):
    """pattern(i) -> (r, flagged)"""
    out = []
    for i in range(50):
        r, flagged = pattern(i)
        out.append(tr(r, i=i, ctx={"risk_atr": 0.5 if flagged else 2.0, "planned_rr": 3.0}))
    return out


def lesson(ts, flag="TIGHT_STOP"):
    return next(x for x in learn_lessons(ts) if x["flag"] == flag)


def test_flag_that_hurts_everywhere_is_confirmed():
    ts = series(lambda i: ((-1.0, True) if i % 2 == 0 else (1.0, False)))
    assert lesson(ts)["verdict"] == "CONFIRMED_OUT_OF_SAMPLE"


def test_flag_that_hurt_only_in_training_is_not_confirmed():
    # first 30 trades: flagged ones lose; last 20: flagged ones win
    ts = series(lambda i: ((-1.0 if i < 30 else 1.5, True) if i % 2 == 0 else (0.5, False)))
    assert lesson(ts)["verdict"] == "NOT_CONFIRMED"


def test_rare_flag_is_insufficient_data():
    ts = series(lambda i: ((-1.0, True) if i in (3, 4) else (0.5, False)))
    assert lesson(ts)["verdict"] == "INSUFFICIENT_DATA"


# ---------------- optional vetoes ----------------
def with_ind(**kw):
    a = base_analysis()
    a["indicators"] = {**a["indicators"], **kw}
    a["fair_value_gaps"][0]["size_in_atr"] = 1.0
    return a


def test_vetoes_are_off_by_default():
    d = SignalGenerator(SignalConfig(), 2.0).decide(with_ind())
    assert d.decision == "SIGNAL" and "context" in d.evidence
    assert d.evidence["context"]["risk_atr"] == pytest.approx((105 - 99.5) / 2.0)


def test_tight_stop_veto_blocks_when_enabled():
    d = SignalGenerator(SignalConfig(min_risk_atr=3.0), 2.0).decide(with_ind())
    assert d.decision == "NO_TRADE" and "VETO_STOP_TOO_TIGHT" in d.reasons


def test_enabled_veto_fails_closed_on_missing_data():
    d = SignalGenerator(SignalConfig(max_rsi=65.0), 2.0).decide(with_ind())  # rsi missing
    assert "VETO_RSI_TOO_HOT" in d.reasons
    ok = SignalGenerator(SignalConfig(max_rsi=65.0), 2.0).decide(with_ind(setup_rsi=50.0))
    assert ok.decision == "SIGNAL"


# ---------------- failure reports ----------------
def test_classification_expected_vs_unexpected():
    assert classify_message("psycopg.OperationalError password authentication failed")["category"] == "DATABASE_CONNECTION"
    assert classify_message("Network error requesting /api/v3/klines after 4 attempt(s): 403 Forbidden")["expected"] is True
    assert classify_message("1d:INSUFFICIENT_HISTORY")["category"] == "DATA_QUALITY"
    bug = classify_message("KeyError: 'sweep_low'")
    assert bug["expected"] is False and bug["category"] == "UNEXPECTED_BUG"


def test_run_guarded_writes_report_and_returns_2(tmp_path, monkeypatch):
    monkeypatch.setattr(failure, "ROOT", tmp_path)

    def boom():
        raise KeyError("sweep_low")

    assert run_guarded("unit_test", boom) == 2
    text = (tmp_path / "reports" / "failure_unit_test.txt").read_text(encoding="utf-8")
    assert "UNEXPECTED_BUG" in text and "traceback" in text and "KeyError" in text
    assert run_guarded("unit_test_ok", lambda: 0) == 0


def test_keyboard_interrupt_is_not_a_crash():
    def interrupted():
        raise KeyboardInterrupt

    assert run_guarded("unit_test_kbd", interrupted) == 130
