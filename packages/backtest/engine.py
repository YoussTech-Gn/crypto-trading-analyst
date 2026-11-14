"""Walk-forward backtester.

At each closed 4H candle t the system sees ONLY: 4H candles <= t and 1D candles whose close time is
<= the close time of candle t. A SIGNAL becomes a limit buy active on candles t+1 .. t+fill_window.

Conservative fill rules:
  * buy limit fills when low <= entry, at the entry price (never better, even on a gap down);
  * on the fill candle only the stop is checked (order of events inside a candle is unknown);
  * afterwards, if one candle touches both stop and target the STOP wins;
  * stop exit = min(stop * (1 - slippage), candle open);  target exit = target price;
  * after max_hold candles the trade exits at the close (TIMEOUT);
  * fees on both sides; R = net pnl / (entry - stop);
  * one position or pending order per symbol at a time; trades still open at the data end are not counted.

Optional exit management (ExitPlan, used by lab recipes only; the default path above is unchanged):
  * levels (partial exit, break-even trigger) are only checked after the fill candle and a stop always wins a tie;
  * a break-even stop takes effect from the NEXT candle (we never assume we moved it inside the candle that triggered it);
  * a break-even stop exits with the same stop slippage and fees as any other stop (it is not free);
  * time exit: after N candles, if the best excursion so far is below a threshold, exit at that candle's close;
  * trailing stop: computed from candles that are already closed, so it only protects from the NEXT candle on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from packages.analysis import AnalysisEngine
from packages.config.settings import AnalysisConfig, BacktestConfig, SignalConfig
from packages.market_data.models import Candle
from packages.signals import SignalGenerator


@dataclass(frozen=True)
class ExitPlan:
    """How a trade is managed after the fill. All values are in R (multiples of the entry-to-stop distance)."""

    fixed_target_r: float | None = None      # replaces the structural target by entry + r * risk
    breakeven_after_r: float | None = None   # once price reaches +r, the stop moves to the entry (from the next candle)
    partial_at_r: float | None = None        # sell `partial_fraction` of the position when price reaches +r
    partial_fraction: float = 0.5
    breakeven_after_partial: bool = False    # after the partial fill the stop moves to the entry (next candle)
    time_exit_bars: int | None = None        # after this many candles ...
    time_exit_min_mfe_r: float = 0.5         # ... exit at the close if the best excursion is still below this
    trail_after_r: float | None = None       # once price has reached +r, the stop trails the highest high ...
    trail_distance_r: float = 1.0            # ... at this distance below it (only ever moves up; from the next candle)
    max_hold_candles: int | None = None      # overrides the global maximum holding time (trend trades need longer)

    @property
    def active(self) -> bool:
        return any(v is not None for v in (self.fixed_target_r, self.breakeven_after_r, self.partial_at_r,
                                           self.time_exit_bars, self.trail_after_r, self.max_hold_candles))

    @property
    def manages_after_fill(self) -> bool:
        return any(v is not None for v in (self.breakeven_after_r, self.partial_at_r, self.time_exit_bars,
                                           self.trail_after_r, self.max_hold_candles))


@dataclass(frozen=True)
class Trade:
    symbol: str
    signal_index: int
    signal_time_ms: int
    entry: float
    stop: float
    target: float
    planned_rr: float
    fill_index: int
    fill_time_ms: int
    exit_index: int
    exit_time_ms: int
    exit_price: float
    exit_reason: str  # STOP | TARGET | TIMEOUT
    r_multiple: float
    bars_held: int
    sweep_level_kind: str = ""
    mae_r: float = 0.0  # worst adverse excursion after the fill, in R (0 = never went against us, 1 = touched the stop)
    mfe_r: float = 0.0  # best favourable excursion in R
    context: dict = field(default_factory=dict)  # entry-time facts (all known BEFORE the trade)
    fee_r: float = 0.0  # fees paid, expressed in R (stop slippage is already inside the exit price)


@dataclass(frozen=True)
class UnfilledSignal:
    symbol: str
    signal_index: int
    signal_time_ms: int
    entry: float
    target: float
    missed_winner: bool  # price reached the target inside the fill window without ever touching the entry


@dataclass
class BacktestResult:
    symbol: str
    trades: list[Trade] = field(default_factory=list)
    unfilled: list[UnfilledSignal] = field(default_factory=list)
    steps: int = 0
    steps_skipped_not_bullish: int = 0
    steps_skipped_data_defect: int = 0
    signals: int = 0
    open_at_end: int = 0
    funnel: dict = field(default_factory=dict)  # check name -> [evaluated, passed] on analysed steps
    analysed_steps: int = 0


def net_r(entry: float, stop: float, exit_price: float, fee_pct: float) -> float:
    fees = fee_pct / 100.0 * (entry + exit_price)
    return (exit_price - entry - fees) / (entry - stop)


def fee_r_of(entry: float, stop: float, exit_price: float, fee_pct: float, size: float = 1.0) -> float:
    return size * fee_pct / 100.0 * (entry + exit_price) / (entry - stop)


def simulate_managed(
    setup: Sequence[Candle], fill: int, entry: float, stop: float, target: float, plan: ExitPlan,
    max_hold: int, fee_pct: float, slip_pct: float,
):
    """Walk a filled trade candle by candle under an ExitPlan.

    Returns (fill, exit_index, blended_exit_price, reason, r_multiple, fee_r) or None while the trade is still open.
    reason: STOP | BREAKEVEN | TRAIL | TARGET | TIMEOUT | TIME_DECAY. R is always measured against the ORIGINAL risk.
    """
    risk = entry - stop
    if plan.max_hold_candles is not None:
        max_hold = plan.max_hold_candles
    cur_stop, stop_moved, trailed = stop, False, False
    remaining, parts = 1.0, []  # parts: (price, size)
    partial_done = False
    pending_be = False
    best_high = entry
    for k in range(fill, len(setup)):
        c = setup[k]
        held = k - fill
        reason = None
        if c.low <= cur_stop:
            parts.append((min(cur_stop * (1.0 - slip_pct / 100.0), c.open), remaining))
            remaining, reason = 0.0, ("TRAIL" if trailed else ("BREAKEVEN" if stop_moved else "STOP"))
        elif k > fill:
            if plan.partial_at_r is not None and not partial_done and c.high >= entry + plan.partial_at_r * risk:
                size = min(plan.partial_fraction, remaining)
                parts.append((entry + plan.partial_at_r * risk, size))
                remaining -= size
                partial_done = True
                if plan.breakeven_after_partial:
                    pending_be = True
            if (plan.breakeven_after_r is not None and not stop_moved and not pending_be
                    and c.high >= entry + plan.breakeven_after_r * risk):
                pending_be = True
            if c.high >= target:
                parts.append((target, remaining))
                remaining, reason = 0.0, "TARGET"
        best_high = max(best_high, c.high)
        if reason is None and remaining > 0:
            mfe = (best_high - entry) / risk
            if plan.time_exit_bars is not None and held >= plan.time_exit_bars and mfe < plan.time_exit_min_mfe_r:
                parts.append((c.close, remaining))
                remaining, reason = 0.0, "TIME_DECAY"
            elif held >= max_hold:
                parts.append((c.close, remaining))
                remaining, reason = 0.0, "TIMEOUT"
        if reason:
            gross = sum(sz * (px - entry) for px, sz in parts) / risk
            fees = sum(fee_r_of(entry, stop, px, fee_pct, sz) for px, sz in parts)
            blended = sum(px * sz for px, sz in parts)
            return fill, k, blended, reason, gross - fees, fees
        if pending_be:
            cur_stop, stop_moved, pending_be = max(cur_stop, entry), True, False
        if plan.trail_after_r is not None and best_high >= entry + plan.trail_after_r * risk:
            new_stop = best_high - plan.trail_distance_r * risk
            if new_stop > cur_stop:
                cur_stop, stop_moved, trailed = new_stop, True, True
    return None


def simulate_order(
    setup: Sequence[Candle], t: int, entry: float, stop: float, target: float,
    fill_window: int, max_hold: int, fee_pct: float, slip_pct: float, plan: ExitPlan | None = None,
):
    """Return (kind, payload, resolved_index). kind: 'TRADE' | 'UNFILLED' | 'OPEN'.

    payload for TRADE is (fill, exit_index, price, reason), or with a managing ExitPlan
    (fill, exit_index, blended_price, reason, r_multiple, fee_r).
    """
    n = len(setup)
    if t + 1 > n - 1:
        return "OPEN", None, n - 1
    end = min(t + fill_window, n - 1)
    fill = next((k for k in range(t + 1, end + 1) if setup[k].low <= entry), None)
    if fill is None:
        if end - t < fill_window:  # window not fully observed yet
            return "OPEN", None, n - 1
        missed = any(setup[k].high >= target for k in range(t + 1, end + 1))
        return "UNFILLED", missed, end
    if plan is not None and plan.manages_after_fill:
        res = simulate_managed(setup, fill, entry, stop, target, plan, max_hold, fee_pct, slip_pct)
        return ("OPEN", None, n - 1) if res is None else ("TRADE", res, res[1])
    for k in range(fill, n):
        c = setup[k]
        held = k - fill
        reason, px = None, None
        if c.low <= stop:
            reason, px = "STOP", min(stop * (1.0 - slip_pct / 100.0), c.open)
        elif k > fill and c.high >= target:
            reason, px = "TARGET", target
        elif held >= max_hold:
            reason, px = "TIMEOUT", c.close
        if reason:
            return "TRADE", (fill, k, px, reason), k
    return "OPEN", None, n - 1


def excursions(setup: Sequence[Candle], fill: int, ex: int, entry: float, stop: float) -> tuple[float, float]:
    risk = entry - stop
    window = setup[fill: ex + 1]
    mae = max(0.0, (entry - min(c.low for c in window)) / risk)
    mfe = max(0.0, (max(c.high for c in window) - entry) / risk)
    return mae, mfe


def closed_daily_count(daily: Sequence[Candle], setup_close_time_ms: int, start: int = 0) -> int:
    """Number of daily candles fully closed by `setup_close_time_ms` (inclusive). Monotonic helper."""
    k = start
    while k < len(daily) and daily[k].close_time_ms <= setup_close_time_ms:
        k += 1
    return k


class Backtester:
    def __init__(
        self, analysis_cfg: AnalysisConfig, signal_cfg: SignalConfig, min_rr: float, bt_cfg: BacktestConfig,
        min_daily: int = 200, min_setup: int = 500, ignore_daily_gate: bool = False,
        tainted_open_times: Sequence[int] = (), taint_radius_before: int = 60, generator=None,
        analysis_cache: dict | None = None, regime_daily: Sequence[Candle] | None = None,
    ) -> None:
        """ignore_daily_gate=True is an EXPERIMENT: signals may fire in any daily regime (recorded in context)."""
        self.engine = AnalysisEngine(analysis_cfg)
        self.ignore_daily_gate = ignore_daily_gate
        self.gen = generator or SignalGenerator(signal_cfg, min_rr, ("DAILY_TREND_BULLISH",) if ignore_daily_gate else ())
        self.signal_cfg = signal_cfg
        # Recipes may carry an ExitPlan; the default signal generator has none (single structural target, as before).
        self.plan: ExitPlan | None = getattr(self.gen, "exit_plan", None)
        # Optional shared cache (symbol, step) -> analysis dict. Analysis does not depend on the recipe, so a lab job can
        # run many recipes over one symbol and analyse each step once. Recipes only read the dict.
        self.cache = analysis_cache
        self.bt = bt_cfg
        self.min_daily = min_daily
        self.min_setup = min_setup
        # 4h candles known to be truncated/irregular in the source data. Steps whose analysis window (radius before)
        # or trade path (expiry + max hold after) touches one are skipped. Decided from data defects only, never from prices.
        self.tainted = frozenset(tainted_open_times)
        self.taint_before = taint_radius_before
        hold = bt_cfg.max_hold_candles
        if self.plan is not None and self.plan.max_hold_candles is not None:
            hold = max(hold, self.plan.max_hold_candles)
        self.taint_after = signal_cfg.expiry_candles + hold
        # Optional market-regime series (for example BTCUSDT daily candles). Its trend is computed from candles that were
        # closed at the time of each step and added to the analysis as analysis["regime"]["btc_daily_bullish"].
        self.regime_daily = regime_daily

    def run(self, symbol: str, daily: Sequence[Candle], setup: Sequence[Candle]) -> BacktestResult:
        res = BacktestResult(symbol)
        bt, n = self.bt, len(setup)
        k, t = 0, self.min_setup - 1
        trend_cache: dict[int, bool] = {}
        regime_cache: dict[int, bool | None] = {}
        pre = [0]
        for c in setup:
            pre.append(pre[-1] + (1 if c.open_time_ms in self.tainted else 0))
        while t < n - 1:
            k = closed_daily_count(daily, setup[t].close_time_ms, k)
            if k < self.min_daily:
                t += 1
                continue
            res.steps += 1
            lo, hi = max(0, t - self.taint_before), min(n - 1, t + self.taint_after)
            if pre[hi + 1] - pre[lo] > 0:
                res.steps_skipped_data_defect += 1
                t += 1
                continue
            dwin = daily[max(0, k - bt.analysis_window_1d): k]
            if k not in trend_cache:
                trend_cache[k] = self.engine.daily_assessment(dwin)[0].bullish
            if not trend_cache[k] and not self.ignore_daily_gate:
                res.steps_skipped_not_bullish += 1
                t += 1
                continue
            swin = setup[max(0, t + 1 - bt.analysis_window_4h): t + 1]
            key = (symbol, setup[t].open_time_ms)
            adict = self.cache.get(key) if self.cache is not None else None
            if adict is None:
                adict = self.engine.analyze(symbol, dwin, swin).to_dict()
                if self.cache is not None:
                    self.cache[key] = adict
            if self.regime_daily is not None:
                kr = closed_daily_count(self.regime_daily, setup[t].close_time_ms)
                if kr not in regime_cache:
                    regime_cache[kr] = (self.engine.daily_assessment(self.regime_daily[max(0, kr - bt.analysis_window_1d): kr])[0].bullish
                                        if kr >= self.min_daily else None)
                adict["regime"] = {"btc_daily_bullish": regime_cache[kr]}
            dec = self.gen.decide(adict)
            res.analysed_steps += 1
            for name, ok in dec.checks.items():
                row = res.funnel.setdefault(name, [0, 0])
                row[0] += 1
                row[1] += 1 if ok else 0
            if dec.decision != "SIGNAL":
                t += 1
                continue
            res.signals += 1
            target, planned_rr = dec.target, dec.risk_reward
            if self.plan is not None and self.plan.fixed_target_r is not None:
                target = dec.entry + self.plan.fixed_target_r * (dec.entry - dec.stop)
                planned_rr = self.plan.fixed_target_r
            kind, payload, end = simulate_order(
                setup, t, dec.entry, dec.stop, target, self.signal_cfg.expiry_candles,
                bt.max_hold_candles, bt.fee_pct_per_side, bt.stop_slippage_pct, self.plan,
            )
            if kind == "TRADE":
                if len(payload) == 6:
                    fill, ex, px, reason, r_net, fee_r = payload
                else:
                    fill, ex, px, reason = payload
                    r_net = net_r(dec.entry, dec.stop, px, bt.fee_pct_per_side)
                    fee_r = fee_r_of(dec.entry, dec.stop, px, bt.fee_pct_per_side)
                mae, mfe = excursions(setup, fill, ex, dec.entry, dec.stop)
                res.trades.append(Trade(
                    symbol, t, setup[t].open_time_ms, dec.entry, dec.stop, target, planned_rr,
                    fill, setup[fill].open_time_ms, ex, setup[ex].open_time_ms, px, reason,
                    r_net, ex - fill,
                    (dec.evidence.get("sweep", {}).get("deepest_level_kind", "")),
                    mae, mfe, dict(dec.evidence.get("context", {})), fee_r,
                ))
            elif kind == "UNFILLED":
                res.unfilled.append(UnfilledSignal(symbol, t, setup[t].open_time_ms, dec.entry, target, bool(payload)))
            else:
                res.open_at_end += 1
                break
            t = max(end, t + 1)
        return res
