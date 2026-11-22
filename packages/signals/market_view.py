"""Market view (ADR-042, ADR-045): what the market does and what each tracked rule waits for. Pure: candles in, dict out.
Shared by scripts/trader_view.py (text), scripts/dashboard.py (HTML) and scripts/notify.py (morning summary)."""

from __future__ import annotations

from packages.signals.explain import (RULE_NAMES, RULE_SHORT, breakout_gap_pct, cell, daily_trend_short, daily_trend_text,
                                      missing_checks, waiting_text)


def market_view(engine, rules: dict, series: dict, w1: int, w4: int) -> dict:
    """series: {symbol: (daily candles, 4h candles)} with closed candles only. BTCUSDT must be present."""
    btc_d, _ = series["BTCUSDT"]
    btc_trend, *_ = engine.daily_assessment(btc_d[-w1:])
    rows, signals, close_calls, up = [], [], [], []
    last_close = 0
    for sym, (d, h) in series.items():
        an = engine.analyze(sym, d[-w1:], h[-w4:]).to_dict()
        an["regime"] = {"btc_daily_bullish": btc_trend.bullish}
        last_close = max(last_close, h[-1].close_time_ms)
        coin = sym.replace("USDT", "")
        if an["daily_trend"]["bullish"]:
            up.append(coin)
        cells = []
        for name, rule in rules.items():
            dec = rule.decide(an)
            cells.append(cell(dec))
            if dec.decision == "SIGNAL":
                signals.append({"coin": coin, "rule": RULE_NAMES.get(name, name), "entry": dec.entry, "stop": dec.stop,
                                "target": dec.target})
            elif len(missing_checks(dec)) == 1:
                extra = ""
                if name.startswith("brk"):
                    gap = breakout_gap_pct(an, "prior_high_55" if "55" in name else "prior_high_20")
                    extra = f" (price is {gap:.1f}% below that level)" if gap is not None and gap > 0 else ""
                close_calls.append({"coin": coin, "rule": RULE_NAMES.get(name, name),
                                    "missing": waiting_text(dec, 1)[len("waiting for "):] + extra})
        rows.append({"coin": coin, "price": an["indicators"]["setup_last_close"], "trend": daily_trend_short(an["daily_trend"]),
                     "cells": cells})
    rows.sort(key=lambda r: (not r["trend"].startswith("UP"),
                             min(0 if c == "SIGNAL" else int(c.split()[0]) for c in r["cells"]), r["coin"]))
    return {
        "last_close_ms": last_close,
        "btc_trend": daily_trend_text({"bullish": btc_trend.bullish, "failed_conditions": list(btc_trend.failed_conditions)}),
        "btc_up": bool(btc_trend.bullish), "up": up, "coins": len(rows), "signals": signals, "close_calls": close_calls,
        "rule_heads": [RULE_SHORT.get(n, n) for n in rules], "rows": rows,
    }
