"""Post-mortem of every trade: why it won or lost, was it expected, was a known weak pattern present.

Definitions
  EXPECTED loss  : the loss stayed within the budgeted risk (<= 1.5 R). Taking this risk was rational.
  UNEXPECTED loss: realised loss beyond 1.5 R (gap through the stop, slippage) - the model's risk estimate was wrong.
  AVOIDABLE flag : a weak pattern known at ENTRY time (tight stop, thin reward-to-risk, ...). Flags describe what could
                   have been vetoed. They only become rules after out-of-sample confirmation (see learn_lessons).
Outcome facts (fast failure, near miss) are descriptive only: they are not known at entry, so they never become vetoes.
"""

from __future__ import annotations

from typing import Sequence

from packages.backtest.engine import Trade

EXPECTED_LOSS_LIMIT_R = 1.5

# entry-time flags: name -> (test, description, suggested config change)
ENTRY_FLAGS = {
    "TIGHT_STOP": (lambda c: c.get("risk_atr") is not None and c["risk_atr"] < 1.0,
                   "stop tighter than 1x ATR (normal market noise hits it)", {"signals.min_risk_atr": 1.0}),
    "THIN_RR": (lambda c: c.get("planned_rr") is not None and c["planned_rr"] < 2.5,
                "planned reward/risk below 2.5 (thin margin against fees)", {"strategy.minimum_reward_to_risk": 2.5}),
    "DEEP_SWEEP": (lambda c: c.get("sweep_penetration_pct") is not None and c["sweep_penetration_pct"] > 1.0,
                   "deep sweep (>1%), may be a real breakdown", {"signals.max_sweep_penetration_pct": 1.0}),
    "TINY_FVG": (lambda c: c.get("fvg_size_atr") is not None and c["fvg_size_atr"] < 0.25,
                 "FVG smaller than 0.25x ATR (weak)", {"signals.min_fvg_size_atr": 0.25}),
    "HOT_RSI": (lambda c: c.get("rsi") is not None and c["rsi"] > 65,
                "RSI high (>65) at entry", {"signals.max_rsi": 65.0}),
    "LOW_VOLUME": (lambda c: c.get("rel_volume") is not None and c["rel_volume"] < 0.8,
                   "weak volume at entry (<0.8 of average)", {"signals.min_relative_volume": 0.8}),
}


def entry_flags(trade: Trade) -> list[str]:
    ctx = trade.context or {}
    return [name for name, (test, _d, _s) in ENTRY_FLAGS.items() if test(ctx)]


def analyze_trade(t: Trade) -> dict:
    flags = entry_flags(t)
    base = {
        "symbol": t.symbol, "signal_time_ms": t.signal_time_ms, "exit_time_ms": t.exit_time_ms,
        "exit_reason": t.exit_reason, "r": round(t.r_multiple, 3), "bars_held": t.bars_held,
        "mae_r": round(t.mae_r, 2), "mfe_r": round(t.mfe_r, 2), "entry_flags": flags,
    }
    if t.r_multiple > 0:
        if t.mae_r >= 0.8:
            cat, why = "LUCKY_WIN", "won, but price nearly hit the stop (dropped 0.8R or more): success by luck, not quality"
        elif t.mae_r < 0.5:
            cat, why = "CLEAN_WIN", "clean win: price barely went against us before the target"
        else:
            cat, why = "NORMAL_WIN", "won after a moderate pullback within the planned risk"
        if t.exit_reason == "TIMEOUT":
            cat, why = "TIMEOUT_WIN", "small win by timeout, target not reached: the idea did not complete"
        return {**base, "outcome": "WIN", "category": cat, "expected": True, "why": why}

    notes = []
    if t.bars_held <= 2:
        notes.append("fast failure: stop hit within two candles of entry (the sweep was probably a continuation down)")
    if t.mfe_r >= 1.5:
        notes.append(f"nearly won: reached +{t.mfe_r:.1f}R then reversed (a trade-management lesson, not an entry lesson)")
    if t.exit_reason == "STOP" and t.r_multiple < -EXPECTED_LOSS_LIMIT_R:
        return {**base, "outcome": "LOSS", "category": "GAP_THROUGH_STOP", "expected": False,
                "why": f"loss of {t.r_multiple:.2f}R is larger than planned (1R): price gapped through the stop. The risk estimate was wrong",
                "notes": notes}
    if t.exit_reason == "TIMEOUT":
        return {**base, "outcome": "LOSS", "category": "TIMEOUT_LOSS", "expected": True,
                "why": "neither stop nor target reached within the hold limit, exited at a loss: the idea did not move (acceptable risk)", "notes": notes}
    return {**base, "outcome": "LOSS", "category": "NORMAL_STOP", "expected": True,
            "why": "stop hit within the planned risk (about 1R): expected, rational risk", "notes": notes}


def _avg(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def flag_stats(trades: Sequence[Trade], flag: str) -> dict:
    test = ENTRY_FLAGS[flag][0]
    w = [t.r_multiple for t in trades if test(t.context or {})]
    wo = [t.r_multiple for t in trades if not test(t.context or {})]
    return {"n_with": len(w), "avg_r_with": _avg(w), "n_without": len(wo), "avg_r_without": _avg(wo)}


def learn_lessons(trades: Sequence[Trade], train_frac: float = 0.6, min_with_train: int = 5,
                  min_with_test: int = 3, margin_r: float = 0.25) -> list[dict]:
    """A flag becomes a CONFIRMED lesson only if it hurt in the TRAIN period (earlier trades) AND still hurts in the
    TEST period (later trades). Otherwise it is NOT_CONFIRMED (probably noise) or INSUFFICIENT_DATA."""
    ordered = sorted(trades, key=lambda t: (t.signal_time_ms, t.symbol))
    cut = int(len(ordered) * train_frac)
    train, test = ordered[:cut], ordered[cut:]
    out = []
    for name, (_t, desc, change) in ENTRY_FLAGS.items():
        tr, te, al = flag_stats(train, name), flag_stats(test, name), flag_stats(ordered, name)
        if al["n_with"] == 0:
            continue
        hurt_train = tr["n_with"] >= min_with_train and tr["n_without"] > 0 and tr["avg_r_with"] < tr["avg_r_without"] - margin_r
        if tr["n_with"] < min_with_train or te["n_with"] < min_with_test:
            verdict = "INSUFFICIENT_DATA"
        elif hurt_train and te["n_without"] > 0 and te["avg_r_with"] < te["avg_r_without"]:
            verdict = "CONFIRMED_OUT_OF_SAMPLE"
        else:
            verdict = "NOT_CONFIRMED"
        out.append({"flag": name, "description": desc, "suggested_change": change, "verdict": verdict,
                    "all": al, "train": tr, "test": te})
    order = {"CONFIRMED_OUT_OF_SAMPLE": 0, "NOT_CONFIRMED": 1, "INSUFFICIENT_DATA": 2}
    return sorted(out, key=lambda x: (order[x["verdict"]], x["flag"]))


def build_postmortem(trades: Sequence[Trade]) -> dict:
    items = [analyze_trade(t) for t in sorted(trades, key=lambda t: (t.exit_time_ms, t.symbol))]
    losses = [i for i in items if i["outcome"] == "LOSS"]
    cats: dict[str, int] = {}
    for i in items:
        cats[i["category"]] = cats.get(i["category"], 0) + 1
    return {
        "trades": len(items),
        "categories": cats,
        "losses": len(losses),
        "expected_losses": sum(1 for i in losses if i["expected"]),
        "unexpected_losses": sum(1 for i in losses if not i["expected"]),
        "losses_with_avoidable_flags": sum(1 for i in losses if i["entry_flags"]),
        "lucky_wins": cats.get("LUCKY_WIN", 0),
        "lessons": learn_lessons(trades),
        "items": items,
    }
