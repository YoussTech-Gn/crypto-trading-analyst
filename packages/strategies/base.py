"""Strategy recipes: a strategy is a choice of parts (context + trigger + entry + exit + optional filters).

Every recipe is a pure function of the analysis dict (same input the baseline signal generator uses),
so the SAME backtester, fills, fees and windows compare them fairly. PAPER ONLY: nothing here places an order.
"""

from __future__ import annotations

from packages.config.settings import SignalConfig
from packages.signals.generator import H4_MS, SignalDecision, make_signal_id

OPEN_FVG_STATUSES = ("UNTOUCHED", "ENTERED")


def pick_target(analysis: dict, entry: float, close: float, stop: float, min_rr: float) -> float | None:
    """First confirmed swing high above the entry that already pays at least min_rr."""
    risk = entry - stop
    if risk <= 0:
        return None
    highs = sorted(s["price"] for s in analysis["setup_swings"] if s["kind"] == "HIGH" and s["price"] > max(entry, close))
    ok = [h for h in highs if (h - entry) / risk >= min_rr]
    return ok[0] if ok else None


def make_context(analysis: dict, entry: float, stop: float, atr: float, rr: float | None,
                 fvg: dict | None = None, sweep: dict | None = None, bullish: bool = True) -> dict:
    ind = analysis["indicators"]
    ef, es = ind.get("daily_ema_fast"), ind.get("daily_ema_slow")
    return {
        "risk_atr": (entry - stop) / atr,
        "planned_rr": rr,
        "fvg_size_atr": fvg.get("size_in_atr") if fvg else None,
        "sweep_penetration_pct": sweep.get("deepest_penetration_pct") if sweep else None,
        "rsi": ind.get("setup_rsi"),
        "rel_volume": ind.get("setup_relative_volume"),
        "ema_gap_pct": ((ef - es) / es * 100.0) if ef and es else None,
        "daily_bullish": bullish,
    }


class Recipe:
    name = ""
    description = ""
    components: dict = {}

    def __init__(self, cfg: SignalConfig, min_rr: float) -> None:
        self.cfg = cfg
        self.min_rr = float(min_rr)

    def params(self) -> dict:
        return {**self.cfg.model_dump(), "min_risk_reward": self.min_rr, "recipe": self.name}

    def decide(self, analysis: dict) -> SignalDecision:  # pragma: no cover - interface
        raise NotImplementedError

    def _finish(self, analysis: dict, checks: dict, entry, stop, target, rr, evidence: dict) -> SignalDecision:
        reasons = tuple(k for k, v in checks.items() if not v)
        ok = not reasons and None not in (entry, stop, target, rr)
        open_ms = analysis["setup_last_open_time_ms"]
        signal_time = open_ms + H4_MS
        return SignalDecision(
            signal_id=make_signal_id(analysis["symbol"], open_ms), symbol=analysis["symbol"],
            decision="SIGNAL" if ok else "NO_TRADE", reasons=reasons, checks=checks,
            setup_candle_open_time_ms=open_ms,
            entry=entry if ok else None, stop=stop if ok else None, target=target if ok else None,
            risk_reward=rr if ok else None,
            signal_time_ms=signal_time if ok else None,
            valid_until_ms=signal_time + self.cfg.expiry_candles * H4_MS if ok else None,
            evidence=evidence, params=self.params(), analysis_version=analysis.get("version", ""),
            signal_version=f"lab-{self.name}",
        )

    def _prepare(self, analysis: dict):
        ind = analysis["indicators"]
        last = analysis["setup_candle_count"] - 1
        close, atr = ind.get("setup_last_close"), ind.get("setup_atr")
        checks = {"DAILY_TREND_BULLISH": bool(analysis["daily_trend"]["bullish"])}
        checks["ATR_AVAILABLE"] = bool(atr) and close is not None
        return last, close, atr, checks, {"last_index": last, "last_close": close, "atr": atr}

    def _risk_block(self, analysis, checks, evidence, entry, stop, close, atr, fvg=None, sweep=None):
        """Shared tail: stop/target/RR checks and context. Returns (target, rr)."""
        checks["STOP_BELOW_ENTRY"] = stop < entry
        checks["PRICE_ABOVE_STOP"] = close > stop
        checks["PRICE_NEAR_ENTRY"] = close <= entry + self.cfg.max_entry_distance_atr * atr
        target = rr = None
        if stop < entry:
            target = pick_target(analysis, entry, close, stop, self.min_rr)
            checks["TARGET_AVAILABLE"] = target is not None
            if target is not None:
                rr = (target - entry) / (entry - stop)
                checks["REWARD_TO_RISK_OK"] = rr >= self.min_rr
                evidence["risk_reward"] = rr
            evidence["context"] = make_context(analysis, entry, stop, atr, rr, fvg, sweep, checks["DAILY_TREND_BULLISH"])
        return target, rr
