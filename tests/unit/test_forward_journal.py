from types import SimpleNamespace

import pytest

from packages.backtest.engine import ExitPlan
from packages.journal.forward import (BACKFILL_MAX_MS, DECISION_WINDOW_MS, DECISIONS, JOURNAL_START_OPEN_MS, TRACKED,
                                      auto_absent, backfill_plan, clustered_ci,
                                      decision_window_open, new_record, owner_r, review, settle, verdict)
from packages.market_data.models import Candle

H4 = 14_400_000


def c(i, o, h, l, cl):
    return Candle("XUSDT", "4h", i * H4, i * H4 + H4 - 1, o, h, l, cl, 1000.0, 1000.0 * cl, 10)


def dec(entry=100.0, stop=95.0, target=110.0, t=0):
    return SimpleNamespace(symbol="XUSDT", setup_candle_open_time_ms=t * H4, entry=entry, stop=stop, target=target,
                           risk_reward=2.0, checks={"DAILY_TREND_BULLISH": True, "RECENT_SELL_SIDE_SWEEP": True},
                           evidence={"sweep": {"deepest_level_kind": "SWING_LOW", "deepest_penetration_pct": 0.4}})


def test_tracked_recipes_are_preregistered():
    assert TRACKED == ("brk55_trail", "brk20_btc_trail", "sweep_only")


def test_record_shows_reasons_for_and_against():
    r = new_record("sweep_only", dec(), None, {"sweep_only": {"avg_r": -0.479, "ci_lower_r": -0.687, "trades": 2066}}, {}, 2 * H4, H4 - 1)
    assert r["status"] == "PENDING" and r["owner"]["decision"] is None
    assert any("closed back above" in x for x in r["reasons_for"])
    assert any("-0.479" in x for x in r["reasons_against"]) and any("not advice" in x for x in r["reasons_against"])


def test_settle_uses_the_backtest_rules_target_and_stop():
    rec = new_record("sweep_only", dec(), None, {}, {}, 0, 0)
    up = [c(0, 100, 101, 99, 100), c(1, 100, 101, 99.5, 100.5), c(2, 101, 111, 100, 110)]
    s = settle(rec, up, 6, 30, 0.1, 0.05)
    assert s["status"] == "CLOSED" and s["exit_reason"] == "TARGET" and s["result_r"] == pytest.approx(2.0 - 0.001 * 210 / 5, rel=1e-6)
    down = [c(0, 100, 101, 99, 100), c(1, 100, 100.5, 94, 95)]
    s2 = settle(rec, down, 6, 30, 0.1, 0.05)
    assert s2["exit_reason"] == "STOP" and s2["result_r"] < -1.0


def test_settle_keeps_waiting_and_reports_unfilled():
    rec = new_record("x", dec(entry=90.0, stop=85.0, target=100.0), None, {}, {}, 0, 0)
    few = [c(0, 100, 101, 99, 100), c(1, 100, 101, 99, 100)]
    assert settle(rec, few, 6, 30, 0.1, 0.05)["status"] == "PENDING"
    many = [c(i, 100, 101, 99, 100) for i in range(10)]
    assert settle(rec, many, 6, 30, 0.1, 0.05)["status"] == "UNFILLED"


def test_settle_with_a_trailing_plan_roundtrips_through_json():
    plan = ExitPlan(trail_after_r=1.0, trail_distance_r=1.0, max_hold_candles=120)
    rec = new_record("brk55_trail", dec(target=100.0 + 50 * 5.0), plan, {}, {}, 0, 0)  # trend recipes: 50R cap
    assert rec["plan"]["trail_after_r"] == 1.0
    path = [c(0, 100, 100, 100, 100), c(1, 100, 106, 99.5, 105), c(2, 105, 112, 104, 111), c(3, 111, 111, 104, 104)]
    s = settle(rec, path, 6, 30, 0.1, 0.05)
    assert s["status"] == "CLOSED" and s["exit_reason"] in ("TRAIL", "STOP")


def test_owner_r_measures_manual_execution():
    rec = new_record("sweep_only", dec(), None, {}, {}, 0, 0)
    rec.update(status="CLOSED", exit_price=110.0, result_r=1.958)
    rec["owner"] = {"decision": "taken", "price": 101.0, "mood": 3, "note": "", "at": ""}
    assert owner_r(rec, 0.1) == pytest.approx((110 - 101) / 5 - 0.001 * 211 / 5)
    rec["owner"]["decision"] = "skipped"
    assert owner_r(rec, 0.1) is None


def test_verdict_only_at_100_and_200():
    t = [i * 7 * 86_400_000 for i in range(250)]
    assert verdict([1.0] * 99, t).startswith("COLLECTING")
    assert verdict([-1.0, -0.5] * 50, t).startswith("KILLED at 100")
    assert verdict([1.0, 0.5] * 50, t).startswith("PASSED at 100")
    noisy = [1.0, -1.0] * 50  # true average 0
    assert verdict(noisy, t).startswith("UNDECIDED")
    assert verdict(noisy * 2, t).startswith("KILLED at 200")


def test_review_compares_owner_and_system():
    recs = []
    for i in range(4):
        r = new_record("sweep_only", dec(t=i), None, {}, {}, 0, 0)
        r.update(status="CLOSED", result_r=1.0 if i % 2 == 0 else -1.0, exit_price=110.0 if i % 2 == 0 else 95.0)
        r["owner"] = {"decision": "taken" if i % 2 == 0 else "skipped", "price": 100.0, "mood": 3, "note": "", "at": ""}
        recs.append(r)
    text = "\n".join(review(recs, 0.1))
    assert "taken 2" in text and "skipped 2" in text and "COLLECTING" in text


def test_absent_is_a_preregistered_decision():
    assert DECISIONS == ("taken", "skipped", "absent")
    assert DECISION_WINDOW_MS == 4 * 3_600_000


def test_no_decision_after_4_hours_becomes_absent_and_freezes():
    rec = new_record("sweep_only", dec(t=0), None, {}, {}, 0, 0)  # candle closes at H4
    assert auto_absent(rec, H4 + DECISION_WINDOW_MS) is rec  # exactly 4 hours: still open
    assert decision_window_open(rec, H4 + DECISION_WINDOW_MS)
    late = auto_absent(rec, H4 + DECISION_WINDOW_MS + 1)
    assert late["owner"]["decision"] == "absent" and late["owner"]["auto"] is True
    assert rec["owner"]["decision"] is None  # original untouched
    assert not decision_window_open(late, H4 + DECISION_WINDOW_MS + 1)
    rec["owner"]["decision"] = "skipped"
    assert auto_absent(rec, 10 * H4) is rec  # an existing decision is never overwritten


def test_absent_counts_for_the_system_but_not_in_taken_vs_skipped():
    recs = []
    for i, (d, r) in enumerate([("taken", 1.0), ("skipped", -1.0), ("absent", 3.0), ("absent", -2.0)]):
        x = new_record("sweep_only", dec(t=i), None, {}, {}, 0, 0)
        x.update(status="CLOSED", result_r=r, exit_price=110.0 if r > 0 else 95.0)
        x["owner"] = {"decision": d, "price": 100.0 if d == "taken" else None, "mood": None, "note": "", "at": ""}
        recs.append(x)
    text = "\n".join(review(recs, 0.1))
    assert "system avg R +0.250" in text  # all 4 closed signals, absent included
    assert "taken 1 (system R +1.000" in text and "skipped 1 (system R -1.000" in text
    assert "absent 2 (system R +0.500" in text


S0 = JOURNAL_START_OPEN_MS


def test_backfill_constants_are_preregistered():
    assert BACKFILL_MAX_MS == 7 * 86_400_000
    assert JOURNAL_START_OPEN_MS == 1_794_657_600_000  # 2026-11-14 12:00 UTC, the first live scan's candle


def test_backfill_covers_every_missed_candle_since_the_last_scan():
    opens = [S0 + i * H4 for i in range(-10, 20)]  # i = 0 is the journal's first candle
    now = S0 + 20 * H4 + 60_000
    idx, gap = backfill_plan(opens, S0 + 5 * H4, now, 1)  # last scan analysed candle 5; asleep for 3+ scans
    assert [opens[i] for i in idx] == [S0 + i * H4 for i in range(6, 20)] and gap is None
    idx, _ = backfill_plan(opens, S0 + 19 * H4, now, 1)  # nothing new
    assert idx == []


def test_backfill_never_reenters_the_backtest_sample():
    opens = [S0 + i * H4 for i in range(-10, 5)]
    idx, gap = backfill_plan(opens, None, S0 + 5 * H4 + 1, 1)  # first scan ever: starts at the journal start
    assert opens[idx[0]] == S0 and gap is None


def test_backfill_stops_at_7_days_and_reports_the_gap():
    week = BACKFILL_MAX_MS // H4  # 42 candles
    opens = [S0 + i * H4 for i in range(0, 60)]
    now = S0 + 60 * H4 + 1  # +1 ms: a candle closed exactly 7 days ago would still count (inclusive)
    idx, gap = backfill_plan(opens, S0, now, 1)  # computer off for 10 days
    assert len(idx) == week and opens[idx[0]] + H4 >= now - BACKFILL_MAX_MS
    assert gap == (S0 + H4, opens[idx[0]] - H4)


def test_backfill_requires_a_full_analysis_window():
    opens = [S0 + i * H4 for i in range(0, 10)]
    idx, _ = backfill_plan(opens, None, S0 + 10 * H4, 5)
    assert idx[0] == 4


def test_review_shows_backfilled_signals_and_gaps():
    r = new_record("sweep_only", dec(t=0), None, {}, {}, 0, 0, backfilled=True)
    assert r["backfilled"] is True
    text = "\n".join(review([r], 0.1, [{"symbol": "XUSDT", "from_ms": S0, "to_ms": S0 + H4}]))
    assert "1 found by backfill" in text and "COVERAGE GAPS" in text and "XUSDT" in text
    assert review([], 0.1) == ["no signals yet"]


# ---- ADR-041: tamper-evident journal ------------------------------------------------------------------------------

def _chain(n=3):
    from packages.journal.forward import chain_append
    recs = []
    for i in range(n):
        chain_append(recs, new_record("sweep_only", dec(t=i), None, {}, {}, 0, 0))
    return recs


def test_hash_chain_detects_edits_insertions_and_deletions():
    from packages.journal.forward import GENESIS, verify_chain
    recs = _chain()
    ok = verify_chain(recs)
    assert ok["ok"] and ok["chained"] == 3 and recs[0]["prev_hash"] == GENESIS and ok["head"] == recs[-1]["hash"]
    edited = [dict(r) for r in recs]
    edited[1]["entry"] = 99.0                                   # move a past entry price
    assert not verify_chain(edited)["ok"]
    assert not verify_chain([recs[0], recs[2]])["ok"]           # delete a signal
    inserted = recs[:1] + [new_record("x", dec(t=9), None, {}, {}, 0, 0)] + recs[1:]
    assert not verify_chain(inserted)["ok"]                     # insert an unchained one


def test_settlement_does_not_break_the_chain_and_old_records_are_allowed_first():
    from packages.journal.forward import chain_append, verify_chain
    recs = _chain(2)
    recs[0] = dict(recs[0], status="CLOSED", result_r=1.5)     # settlement fields are outside the hash
    assert verify_chain(recs)["ok"]
    old = new_record("sweep_only", dec(t=50), None, {}, {}, 0, 0)  # written before the chain existed
    mixed = [old]
    chain_append(mixed, new_record("sweep_only", dec(t=51), None, {}, {}, 0, 0))
    v = verify_chain(mixed)
    assert v["ok"] and v["unchained"] == 1


def test_owner_decision_is_sealed_after_its_window_and_edits_are_detected():
    from packages.journal.forward import seal_owner, verify_chain
    recs = _chain(1)
    r = recs[0]
    r["owner"] = {"decision": "skipped", "price": None, "mood": 2, "note": "", "at": ""}
    assert "owner_seal" not in seal_owner(r, r["candle_open_ms"] + H4 + 60_000)   # still inside the 4h window
    sealed = seal_owner(r, r["candle_open_ms"] + H4 + 5 * 3_600_000)
    assert "owner_seal" in sealed and verify_chain([sealed])["ok"]
    tampered = dict(sealed, owner=dict(sealed["owner"], decision="taken"))
    assert not verify_chain([tampered])["ok"]
