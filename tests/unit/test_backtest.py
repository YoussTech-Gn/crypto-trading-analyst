"""Milestone 5 tests: conservative fills, R maths, no look-ahead, metrics and verdict."""
from __future__ import annotations

import random

import pytest

from packages.backtest import Backtester, Trade, UnfilledSignal, simulate_order, summarize, wilson_interval
from packages.backtest.engine import closed_daily_count, net_r
from packages.backtest.metrics import max_consecutive_losses, max_drawdown_r
from packages.config.settings import AnalysisConfig, BacktestConfig, SignalConfig
from packages.market_data.models import Candle

H4 = 4 * 3_600_000
D1 = 86_400_000
ENTRY, STOP, TARGET = 100.0, 95.0, 110.0
FEE, SLIP = 0.1, 0.05


def c(i, o, h, l, cl, step=H4):
    t = i * step
    return Candle("T", "4h" if step == H4 else "1d", t, t + step - 1, o, h, l, cl, 1.0, 1.0, 1)


def flat(i, price=120.0):
    return c(i, price, price + 1, price - 1, price)  # far above entry, never fills


def sim(candles, t=0, fill_window=6, max_hold=30):
    return simulate_order(candles, t, ENTRY, STOP, TARGET, fill_window, max_hold, FEE, SLIP)


# ---------------- fills and exits ----------------
def test_target_win_r_includes_fees():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 101, 111, 100, 109)]
    kind, (fill, ex, px, reason), end = sim(cs)
    assert (kind, fill, ex, px, reason) == ("TRADE", 1, 2, TARGET, "TARGET")
    assert net_r(ENTRY, STOP, px, FEE) == pytest.approx((10 - 0.001 * 210) / 5)


def test_stop_wins_when_stop_and_target_same_candle():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 100, 111, 94, 100)]
    kind, (fill, ex, px, reason), _ = sim(cs)
    assert reason == "STOP" and px == pytest.approx(STOP * (1 - SLIP / 100))


def test_target_is_not_credited_on_fill_candle():
    cs = [flat(0), c(1, 101, 112, 99, 111), c(2, 111, 113, 105, 112)]
    kind, (fill, ex, px, reason), _ = sim(cs)
    assert fill == 1 and ex == 2 and reason == "TARGET"


def test_fill_candle_that_hits_stop_is_a_loss():
    cs = [flat(0), c(1, 101, 102, 94, 96)]
    kind, (fill, ex, px, reason), _ = sim(cs)
    assert fill == 1 and ex == 1 and reason == "STOP"


def test_gap_below_stop_exits_at_open_not_at_stop():
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 90, 92, 88, 91)]
    kind, (fill, ex, px, reason), _ = sim(cs)
    assert reason == "STOP" and px == 90


def test_fill_is_at_entry_even_on_gap_down_open():
    # open far below entry: we still book the entry price (never better than the limit)
    cs = [flat(0), c(1, 97, 98, 96, 97), c(2, 97, 111, 97, 110)]
    kind, (fill, ex, px, reason), _ = sim(cs)
    assert fill == 1 and reason == "TARGET"
    assert net_r(ENTRY, STOP, TARGET, FEE) < (TARGET - ENTRY) / (ENTRY - STOP)  # fees reduce R


def test_timeout_exits_at_close():
    cs = [flat(0), c(1, 101, 101, 99, 100)] + [c(i, 100, 101, 99, 100.5) for i in range(2, 40)]
    kind, (fill, ex, px, reason), _ = sim(cs, max_hold=30)
    assert reason == "TIMEOUT" and ex - fill == 30 and px == 100.5


def test_unfilled_with_missed_winner():
    cs = [flat(0)] + [c(i, 105, 106 if i < 4 else 111, 103, 105) for i in range(1, 8)]
    kind, missed, end = sim(cs)
    assert kind == "UNFILLED" and missed is True and end == 6


def test_unfilled_without_winner():
    cs = [flat(0)] + [c(i, 105, 106, 103, 105) for i in range(1, 8)]
    kind, missed, _ = sim(cs)
    assert kind == "UNFILLED" and missed is False


def test_incomplete_window_and_open_trade_are_not_counted():
    assert sim([flat(0), flat(1)])[0] == "OPEN"  # window not fully observed
    assert sim([flat(0)])[0] == "OPEN"
    cs = [flat(0), c(1, 101, 101, 99, 100), c(2, 100, 101, 99, 100)]
    assert sim(cs)[0] == "OPEN"  # filled but unresolved at the end of data


# ---------------- no look-ahead ----------------
def test_closed_daily_count_respects_close_time():
    daily = [c(0, 1, 1, 1, 1, D1), c(1, 1, 1, 1, 1, D1), c(2, 1, 1, 1, 1, D1)]
    assert closed_daily_count(daily, 5 * H4 - 1) == 0          # day 0 not closed yet
    assert closed_daily_count(daily, 6 * H4 - 1) == 1          # closes exactly with the 6th 4H candle
    assert closed_daily_count(daily, 11 * H4 - 1) == 1
    assert closed_daily_count(daily, 12 * H4 - 1) == 2


def synthetic():
    from math import sin
    daily, p = [], 100.0
    for i in range(260):
        p = 100 + i * 0.8 + 4 * sin(i / 3)
        daily.append(c(i, p, p + 1, p - 1, p, D1))
    rnd, setup, q = random.Random(5), [], 100.0
    for i in range(260 * 6):
        q += rnd.uniform(-1.2, 1.4)
        setup.append(c(i, q, q + rnd.uniform(0, 1.5), q - rnd.uniform(0, 1.5), q + rnd.uniform(-0.4, 0.4)))
    return daily, setup


def make_bt():
    return Backtester(AnalysisConfig(), SignalConfig(), 2.0, BacktestConfig())


def test_backtester_never_sees_future_candles():
    daily, setup = synthetic()
    bt = make_bt()
    seen = []
    real = bt.gen.decide

    def spy(analysis):
        seen.append((analysis["setup_last_open_time_ms"], analysis["daily_last_open_time_ms"]))
        return real(analysis)

    bt.gen.decide = spy
    bt.run("T", daily, setup)
    assert seen, "no step reached the signal generator"
    for setup_open, daily_open in seen:
        assert daily_open + D1 - 1 <= setup_open + H4 - 1  # last daily candle was closed at decision time


def test_backtest_is_deterministic():
    daily, setup = synthetic()
    a, b = make_bt().run("T", daily, setup), make_bt().run("T", daily, setup)
    assert a.trades == b.trades and a.unfilled == b.unfilled and a.signals == b.signals


def test_one_position_at_a_time():
    daily, setup = synthetic()
    r = make_bt().run("T", daily, setup)
    ordered = sorted(r.trades, key=lambda t: t.signal_index)
    for x, y in zip(ordered, ordered[1:]):
        assert y.signal_index >= x.exit_index


# ---------------- metrics ----------------
def trade(r, i=0, sym="A", reason="TARGET"):
    return Trade(sym, i, i, 100, 95, 110, 2.0, i, i, i + 1, i + 1, 100, reason, r, 1)


def test_wilson_interval_known_values():
    lo, hi = wilson_interval(20, 30)
    assert lo == pytest.approx(0.488, abs=0.005) and hi == pytest.approx(0.808, abs=0.005)
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_drawdown_and_losing_streak():
    ts = [trade(1, 1), trade(-2, 2), trade(1, 3), trade(-1, 4), trade(-1, 5)]
    assert max_drawdown_r(ts) == pytest.approx(3.0)  # peak +1 -> -2 at the end
    assert max_consecutive_losses(ts) == 2


def test_verdict_requires_30_trades():
    twelve = [trade(2.0 if i < 8 else -1.0, i) for i in range(12)]  # 67% wins, only 12 trades
    s = summarize(twelve, [], 12, 30)
    assert s["verdict"] == "INSUFFICIENT_SAMPLE" and any("only 12 trades" in w for w in s["warnings"])


def test_verdict_levels_with_30_trades():
    good = [trade(2.0 if i < 20 else -1.0, i) for i in range(30)]
    assert summarize(good, [], 30, 30)["verdict"] == "PROMISING"
    bad = [trade(-1.0, i) for i in range(30)]
    assert summarize(bad, [], 30, 30)["verdict"] == "NEGATIVE"
    meh = [trade(1.0 if i < 16 else -1.0, i) for i in range(30)]
    assert summarize(meh, [], 30, 30)["verdict"] == "MARGINAL"


def test_summary_counts_missed_winners_and_concentration():
    ts = [trade(1.0, i, "A") for i in range(30)]
    un = [UnfilledSignal("A", 1, 1, 100, 110, True), UnfilledSignal("A", 2, 2, 100, 110, False)]
    s = summarize(ts, un, 32, 30)
    assert s["unfilled_missed_winners"] == 1 and s["fill_rate"] == pytest.approx(30 / 32)
    assert any("one symbol" in w for w in s["warnings"])


# ---------------- funnel and experiment mode ----------------
def test_funnel_counts_checks_on_analysed_steps():
    daily, setup = synthetic()
    r = make_bt().run("T", daily, setup)
    assert r.analysed_steps > 0 and "DAILY_TREND_BULLISH" in r.funnel
    ev, ok = r.funnel["DAILY_TREND_BULLISH"]
    assert ev == r.analysed_steps and ok == ev  # only bullish steps are analysed in normal mode


def test_experiment_mode_analyses_every_step_and_records_regime():
    daily, setup = synthetic()
    normal = make_bt().run("T", daily, setup)
    exp = Backtester(AnalysisConfig(), SignalConfig(), 2.0, BacktestConfig(), ignore_daily_gate=True).run("T", daily, setup)
    assert exp.analysed_steps >= normal.analysed_steps and exp.steps_skipped_not_bullish == 0
    assert all("daily_bullish" in t.context for t in exp.trades)


def test_ignored_check_does_not_block_but_stays_recorded():
    from tests.unit.test_signals import base_analysis
    from packages.signals import SignalGenerator
    a = base_analysis(daily_trend={"bullish": False, "failed_conditions": ["X"], "evidence": {}})
    assert SignalGenerator(SignalConfig(), 2.0).decide(a).decision == "NO_TRADE"
    d = SignalGenerator(SignalConfig(), 2.0, ("DAILY_TREND_BULLISH",)).decide(a)
    assert d.decision == "SIGNAL" and d.checks["DAILY_TREND_BULLISH"] is False
    assert d.evidence["context"]["daily_bullish"] is False
