"""Deterministic signal decision. Pure function of an analysis dict and parameters.

SIGNAL only when EVERY check passes. Otherwise NO_TRADE with the failing checks as reasons.
Checks that cannot be evaluated (their inputs are missing) are omitted from `checks`;
their root cause is already a failed check. PAPER ONLY: nothing here places an order.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

from packages.config.settings import SignalConfig

SIGNAL_VERSION = "signals-1.0"
H4_MS = 4 * 3_600_000
OPEN_FVG_STATUSES = ("UNTOUCHED", "ENTERED")


@dataclass(frozen=True)
class SignalDecision:
    signal_id: str
    symbol: str
    decision: str  # "SIGNAL" | "NO_TRADE"
    reasons: tuple[str, ...]
    checks: dict
    setup_candle_open_time_ms: int
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    risk_reward: float | None = None
    signal_time_ms: int | None = None
    valid_until_ms: int | None = None
    evidence: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    analysis_version: str = ""
    signal_version: str = SIGNAL_VERSION
    paper_only: bool = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["reasons"] = list(self.reasons)
        return d


def make_signal_id(symbol: str, setup_open_time_ms: int) -> str:
    raw = f"{symbol}|{setup_open_time_ms}|{SIGNAL_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class SignalGenerator:
    def __init__(self, config: SignalConfig | None = None, min_risk_reward: float = 2.0,
                 ignored_checks: tuple[str, ...] = ()) -> None:
        """`ignored_checks` is for EXPERIMENTS only (e.g. measuring a filter's value). Never used for live signals."""
        self.config = config or SignalConfig()
        self.min_rr = float(min_risk_reward)
        self.ignored_checks = tuple(ignored_checks)

    def params(self) -> dict:
        return {**self.config.model_dump(), "min_risk_reward": self.min_rr, "ignored_checks": list(self.ignored_checks)}

    def no_data(self, symbol: str, setup_open_time_ms: int, detail: str) -> SignalDecision:
        return SignalDecision(
            signal_id=make_signal_id(symbol, setup_open_time_ms), symbol=symbol, decision="NO_TRADE",
            reasons=(f"DATA_INVALID:{detail}",), checks={"DATA_VALID": False},
            setup_candle_open_time_ms=setup_open_time_ms, params=self.params(),
        )

    def decide(self, analysis: dict) -> SignalDecision:
        cfg = self.config
        symbol = analysis["symbol"]
        open_ms = analysis["setup_last_open_time_ms"]
        last = analysis["setup_candle_count"] - 1
        ind = analysis["indicators"]
        close, atr = ind.get("setup_last_close"), ind.get("setup_atr")
        checks: dict[str, bool] = {}
        evidence: dict = {"last_index": last, "last_close": close, "atr": atr}

        checks["DAILY_TREND_BULLISH"] = bool(analysis["daily_trend"]["bullish"])
        evidence["daily_trend_failed"] = analysis["daily_trend"]["failed_conditions"]

        recent = [e for e in analysis["sweep_events"] if e["sweep_index"] >= last - cfg.sweep_window_candles + 1]
        sweep = max(recent, key=lambda e: e["sweep_index"]) if recent else None
        checks["RECENT_SELL_SIDE_SWEEP"] = sweep is not None
        fvg = None
        if sweep is not None:
            evidence["sweep"] = sweep
            cands = [g for g in analysis["fair_value_gaps"]
                     if g["index"] > sweep["sweep_index"] and g["status"] in OPEN_FVG_STATUSES]
            fvg = max(cands, key=lambda g: g["index"]) if cands else None
            checks["OPEN_FVG_AFTER_SWEEP"] = fvg is not None
        checks["ATR_AVAILABLE"] = bool(atr) and close is not None

        entry = stop = target = rr = None
        if sweep is not None and fvg is not None and checks["ATR_AVAILABLE"]:
            evidence["fvg"] = {k: fvg[k] for k in ("index", "lower", "upper", "status", "formed_time_ms")}
            entry = (fvg["lower"] + fvg["upper"]) / 2.0
            stop = sweep["sweep_low"] - cfg.stop_atr_buffer * atr
            checks["STOP_BELOW_ENTRY"] = stop < entry
            checks["PRICE_ABOVE_STOP"] = close > stop
            checks["PRICE_NEAR_ENTRY"] = close <= entry + cfg.max_entry_distance_atr * atr
            highs = sorted(s["price"] for s in analysis["setup_swings"]
                           if s["kind"] == "HIGH" and s["price"] > max(entry, close))
            if cfg.target_mode == "first_meeting_rr" and stop < entry:
                highs = [h for h in highs if (h - entry) / (entry - stop) >= self.min_rr]
            target = highs[0] if highs else None
            evidence["target_mode"] = cfg.target_mode
            checks["TARGET_AVAILABLE"] = target is not None
            if checks["STOP_BELOW_ENTRY"] and target is not None:
                rr = (target - entry) / (entry - stop)
                checks["REWARD_TO_RISK_OK"] = rr >= self.min_rr
                evidence["risk_reward"] = rr
            if checks["STOP_BELOW_ENTRY"]:
                ef, es = ind.get("daily_ema_fast"), ind.get("daily_ema_slow")
                ctx = {
                    "risk_atr": (entry - stop) / atr,
                    "planned_rr": rr,
                    "fvg_size_atr": fvg.get("size_in_atr"),
                    "sweep_penetration_pct": sweep.get("deepest_penetration_pct"),
                    "rsi": ind.get("setup_rsi"),
                    "rel_volume": ind.get("setup_relative_volume"),
                    "ema_gap_pct": ((ef - es) / es * 100.0) if ef and es else None,
                    "daily_bullish": checks["DAILY_TREND_BULLISH"],
                }
                evidence["context"] = ctx
                # optional vetoes (disabled by default). Missing data fails closed when a veto is enabled.
                if cfg.min_risk_atr > 0:
                    checks["VETO_STOP_TOO_TIGHT"] = ctx["risk_atr"] >= cfg.min_risk_atr
                if cfg.max_sweep_penetration_pct > 0:
                    v = ctx["sweep_penetration_pct"]
                    checks["VETO_SWEEP_TOO_DEEP"] = v is not None and v <= cfg.max_sweep_penetration_pct
                if cfg.min_fvg_size_atr > 0:
                    v = ctx["fvg_size_atr"]
                    checks["VETO_FVG_TOO_SMALL"] = v is not None and v >= cfg.min_fvg_size_atr
                if cfg.max_rsi < 100:
                    v = ctx["rsi"]
                    checks["VETO_RSI_TOO_HOT"] = v is not None and v <= cfg.max_rsi
                if cfg.min_relative_volume > 0:
                    v = ctx["rel_volume"]
                    checks["VETO_LOW_VOLUME"] = v is not None and v >= cfg.min_relative_volume

        reasons = tuple(k for k, v in checks.items() if not v and k not in self.ignored_checks)
        ok = not reasons
        signal_time = open_ms + H4_MS
        return SignalDecision(
            signal_id=make_signal_id(symbol, open_ms), symbol=symbol,
            decision="SIGNAL" if ok else "NO_TRADE", reasons=reasons, checks=checks,
            setup_candle_open_time_ms=open_ms,
            entry=entry if ok else None, stop=stop if ok else None, target=target if ok else None,
            risk_reward=rr if ok else None,
            signal_time_ms=signal_time if ok else None,
            valid_until_ms=signal_time + cfg.expiry_candles * H4_MS if ok else None,
            evidence=evidence, params=self.params(), analysis_version=analysis.get("version", ""),
        )
