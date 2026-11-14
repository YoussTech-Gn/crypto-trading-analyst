"""Backtester + ExitPlan + shared analysis cache, driven by a scripted generator on synthetic candles."""
from __future__ import annotations

from types import SimpleNamespace

from packages.backtest import Backtester, ExitPlan
from packages.config.settings import load_config
from packages.market_data.models import Candle

H4 = 14_400_000
D1 = 86_400_000
SIGNAL_AT = 505


def mk(i, tf="4h", step=H4, o=100.0, h=101.0, lo=99.5, c=100.0):
    t = 1_600_000_000_000 // step * step + i * step
    return Candle("TESTUSDT", tf, t, t + step - 1, o, h, lo, c, 10.0, 1000.0, 5)


def series():
    setup = [mk(i) for i in range(560)]
    setup[506] = mk(506, o=101.0, h=101.5, lo=99.5, c=101.0)   # fills the limit at 100 (fill candle)
    setup[507] = mk(507, o=101.0, h=106.0, lo=100.5, c=105.0)  # reaches +1R (105) but not +2R (110)
    daily = [mk(i - 230, "1d", D1) for i in range(330)]
    return daily, setup


class Scripted:
    """Signals once, on candle SIGNAL_AT: limit 100, stop 95, structural target 110."""

    def __init__(self, plan=None):
        self.exit_plan = plan
        self.calls = 0

    def decide(self, analysis):
        self.calls += 1
        fire = analysis["setup_last_open_time_ms"] == series()[1][SIGNAL_AT].open_time_ms
        return SimpleNamespace(
            decision="SIGNAL" if fire else "NO_TRADE", checks={"X": True}, entry=100.0 if fire else None,
            stop=95.0 if fire else None, target=110.0 if fire else None, risk_reward=2.0 if fire else None,
            evidence={"context": {}},
        )


def run(plan=None, cache=None):
    cfg = load_config()
    daily, setup = series()
    gen = Scripted(plan)
    bt = Backtester(cfg.analysis, cfg.signals, 2.0, cfg.backtest, min_setup=500, ignore_daily_gate=True,
                    generator=gen, analysis_cache=cache)
    return bt.run("TESTUSDT", daily, setup), gen


def test_without_a_plan_the_structural_target_is_used():
    res, _ = run()
    t = res.trades[0]
    # +1R was reached on candle 507 but the structural target (110) never was: the trade times out after 30 candles
    assert res.signals == 1 and t.target == 110.0 and t.exit_reason == "TIMEOUT" and t.mfe_r >= 1.0


def test_fixed_target_plan_overrides_the_structural_target():
    res, _ = run(ExitPlan(fixed_target_r=1.0))
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.exit_reason == "TARGET" and t.target == 105.0 and t.planned_rr == 1.0
    assert 0.8 < t.r_multiple < 1.0            # +1R minus fees
    assert t.fee_r > 0


def test_managed_plan_records_fee_drag_in_r():
    res, _ = run(ExitPlan(partial_at_r=1.0, partial_fraction=0.5, breakeven_after_partial=True, time_exit_bars=1, time_exit_min_mfe_r=5.0))
    # time exit with an unreachable threshold closes the trade at the close of candle 507 (held 1 candle)
    t = res.trades[0]
    assert t.exit_reason == "TIME_DECAY" and t.fee_r > 0 and t.bars_held == 1


def test_shared_cache_gives_identical_results_and_skips_reanalysis():
    cache: dict = {}
    first, _ = run(ExitPlan(fixed_target_r=1.0), cache)
    assert cache  # populated
    n_cached = len(cache)
    second, _ = run(ExitPlan(fixed_target_r=1.0), cache)
    assert len(cache) == n_cached
    assert [t.r_multiple for t in first.trades] == [t.r_multiple for t in second.trades]
    plain, _ = run(ExitPlan(fixed_target_r=1.0))
    assert [t.r_multiple for t in plain.trades] == [t.r_multiple for t in first.trades]


def test_lab_job_runs_every_recipe_over_one_symbol_and_returns_stats():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("run_lab", Path(__file__).resolve().parents[2] / "scripts" / "run_lab.py")
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    cfg = load_config()
    daily, setup = series()
    names = ("fvg_only", "fvg_exit_1r", "fvg_exit_be")
    window, sym, out = lab.work((names, "w", "TESTUSDT", daily, setup, cfg, (), daily))
    assert (window, sym) == ("w", "TESTUSDT") and set(out) == set(names)
    for res in out.values():
        assert set(res) == {"trades", "signals", "unfilled", "missed_winners", "open_at_end", "skipped_defect"}


def test_regime_series_is_added_to_the_analysis_and_is_none_when_too_short():
    cfg = load_config()
    daily, setup = series()
    seen = []

    class Spy(Scripted):
        def decide(self, analysis):
            seen.append(analysis.get("regime"))
            return super().decide(analysis)

    long_regime = [mk(i - 230, "1d", D1) for i in range(330)]
    Backtester(cfg.analysis, cfg.signals, 2.0, cfg.backtest, min_setup=500, ignore_daily_gate=True,
               generator=Spy(), regime_daily=long_regime).run("TESTUSDT", daily, setup)
    assert seen and all(r is not None and isinstance(r["btc_daily_bullish"], bool) for r in seen)
    seen.clear()
    Backtester(cfg.analysis, cfg.signals, 2.0, cfg.backtest, min_setup=500, ignore_daily_gate=True,
               generator=Spy(), regime_daily=long_regime[:50]).run("TESTUSDT", daily, setup)
    assert seen and all(r == {"btc_daily_bullish": None} for r in seen)
