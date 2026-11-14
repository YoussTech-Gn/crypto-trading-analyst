"""Analysis engine. Input: CLOSED candles only (validate first with CandleValidator).
Output: a plain-data AnalysisResult. This is analysis, NOT a trade signal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Sequence

from packages.config.settings import AnalysisConfig
from packages.fvg import detect_bullish_fvgs
from packages.indicators import atr, ema, relative_volume, rsi
from packages.liquidity import build_swing_levels, dedupe_levels, detect_sweeps, group_sweeps, previous_day_levels
from packages.market_data.models import Candle
from packages.market_structure import assess_daily_trend, detect_breaks, detect_swings, label_swings

ANALYSIS_VERSION = "analysis-1.0"


@dataclass(frozen=True)
class AnalysisResult:
    symbol: str
    version: str
    daily_last_open_time_ms: int
    setup_last_open_time_ms: int
    setup_candle_count: int
    daily_trend: dict
    daily_swings: list[dict]
    setup_swings: list[dict]
    structure_breaks: list[dict]
    liquidity_levels: list[dict]
    sweeps: list[dict]
    sweep_events: list[dict]
    fair_value_gaps: list[dict]
    indicators: dict
    note: str = "analysis only - not a trading signal"
    features: dict = field(default_factory=dict)  # extra facts for strategy recipes (added in M6c, additive)

    def to_dict(self) -> dict:
        return asdict(self)


def _pct_rank(values: Sequence[float | None], current: float | None) -> float | None:
    vals = [v for v in values if v is not None]
    if current is None or len(vals) < 20:
        return None
    return sum(1 for v in vals if v < current) / len(vals)


def build_features(daily: Sequence[Candle], setup: Sequence[Candle], s_atr: Sequence[float | None],
                   s_rsi: Sequence[float | None]) -> dict:
    """Extra facts for strategy recipes. Everything is computed from closed candles up to the last one (no look-ahead).

    prior_high_N : highest high of the N candles BEFORE the last one (a close above it is an N-candle breakout)
    recent_low_N : lowest low of the last N candles including the last one
    """
    closes = [c.close for c in setup]
    last = setup[-1]

    def prior_high(n: int):
        return max(c.high for c in setup[-n - 1:-1]) if len(setup) > n else None

    def recent_low(n: int):
        return min(c.low for c in setup[-n:]) if len(setup) >= n else None

    ema20, ema50 = ema(closes, 20), ema(closes, 50)
    atr_pct_series = [(a / c) if a is not None and c else None for a, c in zip(s_atr[-200:], closes[-200:])]
    atr_pct = atr_pct_series[-1] if atr_pct_series else None

    def roc(series: Sequence[Candle], n: int):
        return series[-1].close / series[-1 - n].close - 1.0 if len(series) > n and series[-1 - n].close else None

    return {
        "setup_ema_20": ema20[-1], "setup_ema_50": ema50[-1],
        "setup_prev_close": setup[-2].close if len(setup) > 1 else None,
        "setup_last_open": last.open, "setup_last_high": last.high, "setup_last_low": last.low,
        "prior_high_20": prior_high(20), "prior_high_55": prior_high(55),
        "recent_low_5": recent_low(5), "recent_low_10": recent_low(10), "recent_low_20": recent_low(20),
        "setup_rsi_prev": s_rsi[-2] if len(s_rsi) > 1 else None,
        "setup_roc_24": roc(setup, 24),
        "setup_atr_pct": atr_pct, "setup_atr_pct_rank_200": _pct_rank(atr_pct_series[:-1], atr_pct),
        "daily_roc_20": roc(daily, 20), "daily_roc_60": roc(daily, 60),
    }


class AnalysisEngine:
    def __init__(self, config: AnalysisConfig | None = None) -> None:
        self.config = config or AnalysisConfig()

    def daily_assessment(self, daily: Sequence[Candle]):
        """Daily trend only (cheap). Returns (TrendAssessment, labeled swings, ema_fast list, ema_slow list)."""
        cfg = self.config
        d_close = [c.close for c in daily]
        d_ema_f = ema(d_close, cfg.ema_fast)
        d_ema_s = ema(d_close, cfg.ema_slow)
        d_swings = label_swings(detect_swings(daily, cfg.swing_lookback))
        trend = assess_daily_trend(daily, d_swings, d_ema_f[-1], d_ema_s[-1], cfg.min_confirmed_swings)
        return trend, d_swings, d_ema_f, d_ema_s

    def analyze(
        self, symbol: str, daily: Sequence[Candle], setup: Sequence[Candle]
    ) -> AnalysisResult:
        cfg = self.config
        if not daily or not setup:
            raise ValueError("daily and setup candles are required")
        for series in (daily, setup):
            times = [c.open_time_ms for c in series]
            if times != sorted(set(times)):
                raise ValueError("candles must be strictly ascending by open_time")

        trend, d_swings, d_ema_f, d_ema_s = self.daily_assessment(daily)

        s_swings = label_swings(detect_swings(setup, cfg.swing_lookback))
        breaks = detect_breaks(setup, s_swings)
        levels = dedupe_levels(build_swing_levels(s_swings, cfg.equal_level_tolerance_pct) + previous_day_levels(setup, daily))
        sweeps = detect_sweeps(setup, levels, cfg.min_sweep_penetration_pct)

        s_atr = atr([c.high for c in setup], [c.low for c in setup], [c.close for c in setup], cfg.atr_period)
        fvgs = detect_bullish_fvgs(setup, s_atr)
        s_rsi = rsi([c.close for c in setup], cfg.rsi_period)
        s_rvol = relative_volume([c.volume for c in setup], cfg.relative_volume_period)

        return AnalysisResult(
            symbol=symbol,
            version=ANALYSIS_VERSION,
            daily_last_open_time_ms=daily[-1].open_time_ms,
            setup_last_open_time_ms=setup[-1].open_time_ms,
            setup_candle_count=len(setup),
            daily_trend={"bullish": trend.bullish, "failed_conditions": list(trend.failed_conditions), "evidence": trend.evidence},
            daily_swings=[asdict(s) for s in d_swings],
            setup_swings=[asdict(s) for s in s_swings],
            structure_breaks=[asdict(b) for b in breaks],
            liquidity_levels=[asdict(l) for l in levels],
            sweeps=[asdict(s) for s in sweeps],
            sweep_events=group_sweeps(sweeps),
            fair_value_gaps=[asdict(g) for g in fvgs],
            indicators={
                "setup_last_close": setup[-1].close,
                "setup_rsi": s_rsi[-1],
                "setup_atr": s_atr[-1],
                "setup_relative_volume": s_rvol[-1],
                "daily_ema_fast": d_ema_f[-1],
                "daily_ema_slow": d_ema_s[-1],
            },
            features=build_features(daily, setup, s_atr, s_rsi),
        )
