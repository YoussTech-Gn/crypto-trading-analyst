"""M7-FG1 (ADR-034): learn from every 4H candle, walk-forward, judge with the pre-registered kill rule.

  python scripts/run_m7.py            (offline, reads data/cache; about 2-5 minutes)
Output: reports/m7_fg1.txt and .json. No download, no orders.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from packages.learning.dataset import FEATURES, build_dataset  # noqa: E402
from packages.learning.model import (H4, PURGE, FrequencyTable, Logistic, clustered_mean_ci, folds,  # noqa: E402
                                     one_position_per_symbol, week_bootstrap, weighted_auc)
from packages.reporting import run_guarded  # noqa: E402
from scripts.run_lab import BASKETS  # noqa: E402

FIRST_TEST = int(datetime(2021, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
ERAS = (("2021-12..2022", 0, int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)),
        ("2023..2024", int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000), int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)),
        ("2025..2026", int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000), 1 << 62))
CONTROL = ["btc_d_bull", "atr_pct"]


def main() -> int:
    t0 = time.time()
    anchor = json.loads((ROOT / "knowledge" / "overnight_as_of.json").read_text())["as_of_ms"]
    d = build_dataset(ROOT / "data" / "cache", BASKETS["main"].split(","), BASKETS["alt"].split(","))
    keep = d["time"] + (31 * H4) <= anchor
    T, B, S = d["time"][keep], d["basket"][keep], d["sym"][keep]
    y = (d["y_r"][keep] > 0).astype(float)
    R, R2, YB = d["y_r"][keep], d["y2_r"][keep], d["y_beta"][keep]
    X = np.column_stack([d[k][keep] for k in FEATURES])
    W = 1.0 / d["active"][keep]
    syms = d["symbols"]
    is_btc = S == int(np.flatnonzero(syms == "BTCUSDT")[0])
    ci = [FEATURES.index(k) for k in CONTROL]
    week = T // (7 * 86_400_000)
    rng = np.random.default_rng(7)
    log = [f"dataset rows={len(T)} (main {int((B == 0).sum())}, alt {int((B == 1).sum())}), symbols={len(syms)}, built in {time.time() - t0:.0f}s"]

    p_lr, p_ft, p_ct, p_sh = (np.full(len(T), np.nan) for _ in range(4))
    fold_id = np.full(len(T), -1)
    leak_checks = []
    top_feats_log = []
    for fi, (a, b) in enumerate(folds(T, FIRST_TEST)):
        tr = (B == 0) & (T < a - PURGE * H4)
        te = (T >= a) & (T < b)
        if te.sum() == 0 or tr.sum() < 1000:
            continue
        leak_checks.append(bool(T[tr].max() + 31 * H4 <= T[te].min()))
        lr = Logistic().fit(X[tr], y[tr], W[tr])
        p_lr[te] = lr.predict(X[te])
        top3 = list(np.argsort(-np.abs(lr.beta[1:]))[:3])
        top_feats_log.append([FEATURES[j] for j in top3])
        p_ft[te] = FrequencyTable(top3).fit(X[tr], y[tr], W[tr], week[tr]).predict(X[te])
        p_ct[te] = Logistic().fit(X[tr][:, ci], y[tr], W[tr]).predict(X[te][:, ci])
        p_sh[te] = Logistic().fit(X[tr], rng.permutation(y[tr]), W[tr]).predict(X[te])
        fold_id[te] = fi
    oos = fold_id >= 0
    log.append(f"folds={fold_id.max() + 1}, out-of-sample rows={int(oos.sum())}, leakage boundary checks all passed={all(leak_checks)}")

    res: dict = {"baskets": {}}
    kills: list[str] = []
    L = [f"M7-FG1 LEARNING ENGINE (ADR-034, pre-registered)  out-of-sample 2021-12 .. anchor",
         "label: long at open[t+1], +2.0 ATR target / -1.5 ATR stop, 30 candles, stop wins ties, after fees and slippage", ""] + log
    sh_auc = weighted_auc(p_sh[oos & (B == 0)], y[oos & (B == 0)])
    L.append(f"shuffled-label control AUC (main) = {sh_auc:.4f}  (must be 0.50 +/- 0.01)")
    if abs(sh_auc - 0.5) > 0.01:
        kills.append(f"LEAKAGE: shuffled-label AUC {sh_auc:.4f} outside 0.50 +/- 0.01")
    if not all(leak_checks):
        kills.append("LEAKAGE: a train row's label overlaps a test fold")
    for bk, bname in ((0, "MAIN"), (1, "ALT (never trained on)")):
        m = oos & (B == bk)
        tm, yy = T[m], y[m]
        auc = weighted_auc(p_lr[m], yy)
        auc_c = weighted_auc(p_ct[m], yy)
        auc_f = weighted_auc(p_ft[m], yy)
        pl, pc = p_lr[m], p_ct[m]
        lo, hi = week_bootstrap(tm, lambda w: weighted_auc(pl, yy, w) - weighted_auc(pc, yy, w))
        auc_y2 = weighted_auc(pl, (R2[m] > 0).astype(float))
        nb = m & ~is_btc
        auc_beta = weighted_auc(p_lr[nb], YB[nb])
        # top decile per fold
        top = np.zeros(len(T), dtype=bool)
        for f in np.unique(fold_id[m]):
            mf = m & (fold_id == f)
            thr = np.quantile(p_lr[mf], 0.9)
            top |= mf & (p_lr >= thr)
        idx = np.flatnonzero(top)
        idx = idx[np.argsort(T[idx], kind="stable")]
        kept = one_position_per_symbol(idx, T, S)
        mean_r, lo_r, hi_r, G = clustered_mean_ci(R[kept], T[kept])
        base_r = clustered_mean_ci(R[m], T[m])[0]
        cal = abs(p_lr[top].mean() - y[top].mean())
        eras = {}
        for name, e0, e1 in ERAS:
            em = (T[kept] >= e0) & (T[kept] < e1)
            eras[name] = (float(R[kept][em].mean()) if em.any() else float("nan"), int(em.sum()))
        L += ["", f"== {bname}: {int(m.sum())} rows, base win rate {yy.mean():.3f}, base avg R {base_r:+.3f}",
              f"   AUC logistic {auc:.4f} | control [btc_d_bull, atr_pct] {auc_c:.4f} | frequency table {auc_f:.4f}",
              f"   AUC minus control {auc - auc_c:+.4f}, week-bootstrap 95% [{lo:+.4f}, {hi:+.4f}]",
              f"   diagnostics (cannot change the verdict): AUC on +1.5/-1.0 label {auc_y2:.4f}; on beta-stripped label {auc_beta:.4f}",
              f"   top decile: predicted {p_lr[top].mean():.3f} vs realised {y[top].mean():.3f} (calibration error {cal:.3f})",
              f"   top-decile trades (1 position/symbol): {len(kept)} trades, avg R {mean_r:+.3f}, week-clustered 95% [{lo_r:+.3f}, {hi_r:+.3f}], {G} weeks",
              "   by era: " + ", ".join(f"{k} {v[0]:+.3f} ({v[1]} trades)" for k, v in eras.items())]
        tag = "MAIN" if bk == 0 else "ALT"
        if auc < 0.53:
            kills.append(f"(1) {tag} AUC {auc:.4f} < 0.53")
        if auc - auc_c < 0.02 or lo <= 0:
            kills.append(f"(1) {tag} AUC minus control {auc - auc_c:+.4f} (lower bound {lo:+.4f}) does not clear +0.02 / 0")
        if lo_r <= 0:
            kills.append(f"(2) {tag} top-decile trades lower bound {lo_r:+.3f} <= 0")
        if sum(1 for v in eras.values() if v[1] and v[0] < 0) >= 2:
            kills.append(f"(3) {tag} top-decile avg R negative in >= 2 eras")
        if cal > 0.05:
            kills.append(f"(4) {tag} calibration error {cal:.3f} > 0.05")
        res["baskets"][tag] = {"rows": int(m.sum()), "auc": auc, "auc_control": auc_c, "auc_freq": auc_f, "delta_ci": [lo, hi],
                               "auc_y2": auc_y2, "auc_beta": auc_beta, "top_pred": float(p_lr[top].mean()),
                               "top_real": float(y[top].mean()), "trades": len(kept), "avg_r": mean_r, "ci_r": [lo_r, hi_r],
                               "eras": eras}
    from collections import Counter
    tf = Counter(f for fs in top_feats_log for f in fs)
    L += ["", "most influential features (top 3 by |coefficient| per fold, count of folds): " + ", ".join(f"{k} {v}" for k, v in tf.most_common(8))]
    verdict = "REJECTED" if kills else "SURVIVES (provisional)"
    L += ["", f"VERDICT: {verdict}"] + [f"  KILL {k}" for k in kills] + [f"\nelapsed {time.time() - t0:.0f}s"]
    text = "\n".join(L) + "\n"
    (ROOT / "reports" / "m7_fg1.txt").write_text(text, encoding="utf-8")
    res.update({"verdict": verdict, "kills": kills, "shuffled_auc": sh_auc, "top_features": tf.most_common(12)})
    (ROOT / "reports" / "m7_fg1.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(run_guarded("run_m7", main))
