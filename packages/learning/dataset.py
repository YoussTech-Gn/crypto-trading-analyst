"""Build the M7 dataset from the candle cache (ADR-034). Vectorised with numpy, no look-ahead in features.

Every feature of row t uses candles up to and including the 4H candle t (and daily candles CLOSED by then).
Labels use candles t+1 .. t+30 only. Exact formulas are listed in docs/DECISIONS.md ADR-034.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

H4 = 14_400_000
WARMUP = 200
HORIZON = 30
FEE = 0.001
STOP_SLIP = 0.0005

FEATURES = (
    "dist_ema20_atr", "dist_ema50_atr", "dist_high20_atr", "dist_low20_atr", "rsi14", "rel_volume", "roc6", "roc24",
    "atr_pct", "atr_pct_rank200", "d_roc20", "d_roc60", "d_bull", "bars_since_fvg", "dist_fvg_top_atr",
    "bars_since_sweep", "break20", "btc_d_bull", "btc_roc6", "btc_roc24", "rel_roc6", "rel_roc24", "rel_d_roc20",
    "xs_rank_roc24", "xs_rank_relvol",
)


def load_cache_arrays(path: Path) -> dict[str, np.ndarray] | None:
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))["candles"]
    if not rows:
        return None
    a = np.asarray(rows, dtype=float)
    a = a[np.argsort(a[:, 0])]
    return {"open_time": a[:, 0].astype(np.int64), "close_time": a[:, 1].astype(np.int64), "o": a[:, 2], "h": a[:, 3],
            "l": a[:, 4], "c": a[:, 5], "v": a[:, 6]}


# ------------------------------------------------------------------------------------------- indicators
def ema(x: np.ndarray, n: int) -> np.ndarray:
    out, k, prev = np.empty_like(x), 2.0 / (n + 1), x[0]
    for i, v in enumerate(x):
        prev = v if i == 0 else v * k + prev * (1 - k)
        out[i] = prev
    return out


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    if len(x) < n:
        return out
    prev = np.mean(x[:n])
    out[n - 1] = prev
    for i in range(n, len(x)):
        prev = (prev * (n - 1) + x[i]) / n
        out[i] = prev
    return out


def atr14(h, l, c):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return wilder(tr, 14)


def rsi14(c):
    d = np.diff(c, prepend=c[0])
    up, dn = wilder(np.maximum(d, 0), 14), wilder(np.maximum(-d, 0), 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = up / dn
        r = 100 - 100 / (1 + rs)
    r[(dn == 0) & (up > 0)] = 100.0
    return r


def shift(x, k, fill=np.nan):
    out = np.full_like(x, fill, dtype=float)
    if k > 0:
        out[k:] = x[:-k]
    elif k < 0:
        out[:k] = x[-k:]
    else:
        out[:] = x
    return out


def rolling_prev(x, n, fn):
    """fn over x[t-n .. t-1] (previous n values, excluding t)."""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x, n)  # w[i] = x[i .. i+n-1]
    out[n:] = fn(w[:-1], axis=1)
    return out


def bars_since(flag: np.ndarray, cap: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Bars since the last True (0 = this bar), capped; and the index of that bar (-1 if none)."""
    idx = np.where(flag, np.arange(len(flag)), -1)
    last = np.maximum.accumulate(idx)
    since = np.where(last >= 0, np.arange(len(flag)) - last, cap).astype(float)
    return np.minimum(since, cap), last


def pct_rank_window(x, n):
    """Percentile of x[t] among x[t-n+1 .. t]."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x, n)
    out[n - 1:] = (w <= w[:, -1:]).sum(axis=1) / n
    return out


# ------------------------------------------------------------------------------------------- labels
def barrier_label(o, h, l, c, atr, up_atr, dn_atr, horizon=HORIZON):
    """Net R of a long entered at open[t+1] with target +up_atr*ATR[t] and stop -dn_atr*ATR[t]; stop wins ties."""
    n = len(c)
    e = shift(o, -1)
    risk = dn_atr * atr
    stop, tgt = e - risk, e + up_atr * atr
    exit_px = np.full(n, np.nan)
    done = np.zeros(n, dtype=bool)
    for k in range(1, horizon + 1):
        hk, lk, ok = shift(h, -k), shift(l, -k), shift(o, -k)
        hs = ~done & (lk <= stop)
        exit_px[hs] = np.minimum(stop[hs], ok[hs]) * (1 - STOP_SLIP)   # a gap below the stop fills at the open
        done |= hs
        ht = ~done & (hk >= tgt)
        exit_px[ht] = tgt[ht]
        done |= ht
    last = shift(c, -horizon)
    exit_px[~done] = last[~done]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (exit_px - e) / risk - FEE * (e + exit_px) / risk
    return r


@dataclass
class SymbolFrame:
    symbol: str
    open_time: np.ndarray
    X: dict[str, np.ndarray]
    y_r: np.ndarray        # primary net R (+2.0/-1.5 ATR)
    y2_r: np.ndarray       # secondary net R (+1.5/-1.0 ATR)
    ret18: np.ndarray      # open[t+1] -> close[t+18] simple return (for the beta-stripped label)
    valid: np.ndarray


def daily_aligned(d: dict, close_time_4h: np.ndarray):
    """Daily features from the last daily candle CLOSED at or before each 4H close."""
    dc = d["c"]
    e50 = ema(dc, 50)
    roc20 = dc / shift(dc, 20) - 1
    roc60 = dc / shift(dc, 60) - 1
    bull = (dc > e50).astype(float)
    bull[:60] = np.nan
    j = np.searchsorted(d["close_time"], close_time_4h, side="right") - 1
    ok = j >= 0
    jj = np.where(ok, j, 0)
    pick = lambda a: np.where(ok, a[jj], np.nan)
    return pick(roc20), pick(roc60), pick(bull)


def build_symbol(symbol: str, a4: dict, a1: dict) -> SymbolFrame:
    o, h, l, c, v = a4["o"], a4["h"], a4["l"], a4["c"], a4["v"]
    n = len(c)
    atr = atr14(h, l, c)
    e20, e50 = ema(c, 20), ema(c, 50)
    hi20, lo20 = rolling_prev(h, 20, np.max), rolling_prev(l, 20, np.min)
    vmean = rolling_prev(v, 20, np.mean)
    with np.errstate(divide="ignore", invalid="ignore"):
        X = {
            "dist_ema20_atr": (c - e20) / atr, "dist_ema50_atr": (c - e50) / atr,
            "dist_high20_atr": (c - hi20) / atr, "dist_low20_atr": (c - lo20) / atr,
            "rsi14": rsi14(c), "rel_volume": v / vmean,
            "roc6": c / shift(c, 6) - 1, "roc24": c / shift(c, 24) - 1, "atr_pct": atr / c,
        }
    X["atr_pct_rank200"] = pct_rank_window(np.nan_to_num(X["atr_pct"], nan=-1.0), 200)
    X["d_roc20"], X["d_roc60"], X["d_bull"] = daily_aligned(a1, a4["open_time"] + H4 - 1)
    fvg = np.zeros(n, dtype=bool)
    fvg[2:] = l[2:] > h[:-2]
    X["bars_since_fvg"], last_fvg = bars_since(fvg)
    top = np.where(last_fvg >= 0, l[np.maximum(last_fvg, 0)], np.nan)
    X["dist_fvg_top_atr"] = np.clip((c - top) / atr, -10, 10)
    sweep = (l < lo20) & (c > lo20)
    X["bars_since_sweep"], _ = bars_since(np.nan_to_num(sweep, nan=0).astype(bool))
    X["break20"] = (c > hi20).astype(float)
    y_r = barrier_label(o, h, l, c, atr, 2.0, 1.5)
    y2_r = barrier_label(o, h, l, c, atr, 1.5, 1.0)
    ret18 = shift(c, -18) / shift(o, -1) - 1
    # validity: warm-up, full horizon ahead, no gap in [t-200, t+30]
    gap = np.zeros(n, dtype=np.int64)
    gap[1:] = (np.diff(a4["open_time"]) != H4).astype(np.int64)
    cg = np.cumsum(gap)
    idx = np.arange(n)
    lo_i, hi_i = np.clip(idx - WARMUP, 0, n - 1), np.clip(idx + HORIZON, 0, n - 1)
    no_gap = (cg[hi_i] - cg[lo_i]) == 0
    valid = (idx >= WARMUP) & (idx + HORIZON < n) & no_gap & np.isfinite(atr) & (atr > 0) & np.isfinite(y_r)
    return SymbolFrame(symbol, a4["open_time"], X, y_r, y2_r, ret18, valid)


def build_dataset(cache_dir: Path, main: list[str], alt: list[str]) -> dict[str, np.ndarray]:
    frames: list[SymbolFrame] = []
    for sym in main + alt:
        a4 = load_cache_arrays(cache_dir / f"{sym}_4h.json")
        a1 = load_cache_arrays(cache_dir / f"{sym}_1d.json")
        if a4 is None or a1 is None or len(a4["c"]) < WARMUP + HORIZON + 10:
            continue
        frames.append(build_symbol(sym, a4, a1))
    btc = next(f for f in frames if f.symbol == "BTCUSDT")
    bt = {t: i for i, t in enumerate(btc.open_time)}
    cols = {k: [] for k in FEATURES}
    meta = {"time": [], "sym": [], "basket": [], "y_r": [], "y2_r": [], "y_beta": []}
    names = [f.symbol for f in frames]
    for si, f in enumerate(frames):
        bi = np.array([bt.get(t, -1) for t in f.open_time])
        has = bi >= 0
        b = np.where(has, bi, 0)
        g = lambda arr: np.where(has, arr[b], np.nan)
        extra = {"btc_d_bull": g(btc.X["d_bull"]), "btc_roc6": g(btc.X["roc6"]), "btc_roc24": g(btc.X["roc24"])}
        extra["rel_roc6"] = f.X["roc6"] - extra["btc_roc6"]
        extra["rel_roc24"] = f.X["roc24"] - extra["btc_roc24"]
        extra["rel_d_roc20"] = f.X["d_roc20"] - g(btc.X["d_roc20"])
        y_beta = (f.ret18 - g(btc.ret18) > 0).astype(float)
        m = f.valid & has
        for k in FEATURES:
            if k.startswith("xs_"):
                continue
            src = extra[k] if k in extra else f.X[k]
            cols[k].append(src[m])
        meta["time"].append(f.open_time[m])
        meta["sym"].append(np.full(m.sum(), si))
        meta["basket"].append(np.full(m.sum(), 0 if f.symbol in main else 1))
        meta["y_r"].append(f.y_r[m])
        meta["y2_r"].append(f.y2_r[m])
        meta["y_beta"].append(y_beta[m])
    out = {k: np.concatenate(v) for k, v in meta.items()}
    for k in FEATURES:
        if not k.startswith("xs_"):
            out[k] = np.concatenate(cols[k])
    # cross-sectional percentile ranks at each time among all active symbols
    t = out["time"]
    for src, dst in (("roc24", "xs_rank_roc24"), ("rel_volume", "xs_rank_relvol")):
        out[dst] = xs_rank(t, out[src])
    order = np.argsort(t, kind="stable")
    for k in list(out):
        out[k] = out[k][order]
    _, inv, counts = np.unique(out["time"], return_inverse=True, return_counts=True)
    out["active"] = counts[inv].astype(float)
    out["symbols"] = np.array(names)
    return out


def xs_rank(t: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Percentile rank of x within rows sharing the same t (ties averaged by order; NaN stays NaN)."""
    xx = np.where(np.isfinite(x), x, -np.inf)
    order = np.lexsort((xx, t))
    ts = t[order]
    starts = np.r_[0, np.flatnonzero(np.diff(ts)) + 1]
    sizes = np.diff(np.r_[starts, len(ts)])
    pos = np.arange(len(ts)) - np.repeat(starts, sizes)
    size = np.repeat(sizes, sizes)
    r = np.empty(len(x))
    r[order] = (pos + 1) / size
    r[~np.isfinite(x)] = np.nan
    return r
