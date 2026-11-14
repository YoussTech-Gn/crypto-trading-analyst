"""Walk-forward learners and metrics for M7 (ADR-034). numpy only.

Every statistic that is fitted (medians, means, standard deviations, bins, priors) is fitted on the TRAIN rows of a fold.
"""

from __future__ import annotations

import math

import numpy as np

H4 = 14_400_000
WEEK = 7 * 86_400_000
PURGE = 42


# ------------------------------------------------------------------------------------------- logistic regression
class Logistic:
    """L2-regularised logistic regression by Newton steps, with per-row weights. Missing values -> train median."""

    def __init__(self, l2: float = 1.0, iters: int = 30):
        self.l2, self.iters = l2, iters

    def _prep(self, X):
        Z = np.where(np.isfinite(X), X, self.med)
        return np.column_stack([np.ones(len(Z)), (Z - self.mu) / self.sd])

    def fit(self, X, y, w):
        self.med = np.nanmedian(X, axis=0)
        self.med = np.where(np.isfinite(self.med), self.med, 0.0)
        Z = np.where(np.isfinite(X), X, self.med)
        self.mu, self.sd = Z.mean(axis=0), Z.std(axis=0)
        self.sd[self.sd == 0] = 1.0
        A = self._prep(X)
        w = w / w.mean()
        beta = np.zeros(A.shape[1])
        reg = np.full(A.shape[1], self.l2)
        reg[0] = 0.0
        for _ in range(self.iters):
            p = 1 / (1 + np.exp(-np.clip(A @ beta, -30, 30)))
            g = A.T @ (w * (p - y)) + reg * beta
            H = (A * (w * p * (1 - p))[:, None]).T @ A + np.diag(reg)
            step = np.linalg.solve(H, g)
            beta -= step
            if np.max(np.abs(step)) < 1e-7:
                break
        self.beta = beta
        return self

    def predict(self, X):
        return 1 / (1 + np.exp(-np.clip(self._prep(X) @ self.beta, -30, 30)))


# ------------------------------------------------------------------------------------------- frequency table
class FrequencyTable:
    """Pattern buckets on k features (tertiles fitted in train). A bucket counts only if it was seen in >= min_weeks
    distinct weeks; its rate is shrunk toward the train base rate with `prior` pseudo-rows."""

    def __init__(self, cols: list[int], min_weeks: int = 25, prior: float = 50.0):
        self.cols, self.min_weeks, self.prior = cols, min_weeks, prior

    def _codes(self, X):
        code = np.zeros(len(X), dtype=np.int64)
        for j, c in enumerate(self.cols):
            x = X[:, c]
            b = np.digitize(np.where(np.isfinite(x), x, self.cuts[j][0]), self.cuts[j])
            code = code * 3 + b
        return code

    def fit(self, X, y, w, week):
        self.cuts = [np.nanquantile(X[:, c], [1 / 3, 2 / 3]) for c in self.cols]
        code = self._codes(X)
        self.base = float(np.average(y, weights=w))
        self.rate = {}
        for k in np.unique(code):
            m = code == k
            if len(np.unique(week[m])) < self.min_weeks:
                continue
            wn = w[m].sum() / w.mean()
            self.rate[int(k)] = (np.average(y[m], weights=w[m]) * wn + self.base * self.prior) / (wn + self.prior)
        return self

    def predict(self, X):
        return np.array([self.rate.get(int(k), self.base) for k in self._codes(X)])


# ------------------------------------------------------------------------------------------- metrics
def weighted_auc(score, y, w=None):
    """AUC = P(score of a random positive > score of a random negative), weights = row multiplicities. Ties count half."""
    w = np.ones(len(y)) if w is None else w
    order = np.argsort(score, kind="mergesort")
    s, yy, ww = score[order], y[order], w[order]
    pos, neg = ww * (yy == 1), ww * (yy == 0)
    # group ties
    starts = np.r_[0, np.flatnonzero(np.diff(s)) + 1]
    gp, gn = np.add.reduceat(pos, starts), np.add.reduceat(neg, starts)
    neg_below = np.cumsum(gn) - gn
    num = np.sum(gp * (neg_below + 0.5 * gn))
    den = gp.sum() * gn.sum()
    return num / den if den > 0 else float("nan")


def week_bootstrap(time_ms, stat_fn, n_boot=500, seed=7):
    """Resample calendar weeks with replacement; stat_fn(weights) -> value. Returns (2.5%, 97.5%)."""
    wk = time_ms // WEEK
    uniq, inv = np.unique(wk, return_inverse=True)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        cnt = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
        vals.append(stat_fn(cnt[inv].astype(float)))
    vals = np.sort(np.array(vals))
    return float(vals[int(0.025 * n_boot)]), float(vals[int(0.975 * n_boot) - 1])


def clustered_mean_ci(x, time_ms, z=1.96):
    """Mean with a week-clustered (Liang-Zeger) standard error; returns (mean, lower, upper, n_clusters)."""
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan"), 0
    m = x.mean()
    wk = time_ms // WEEK
    uniq, inv = np.unique(wk, return_inverse=True)
    G = len(uniq)
    S = np.bincount(inv, weights=x - m)
    se_cl = math.sqrt(G / max(G - 1, 1) * np.sum(S ** 2)) / n
    se_naive = x.std(ddof=1) / math.sqrt(n)
    se = max(se_cl, se_naive)
    return float(m), float(m - z * se), float(m + z * se), G


def one_position_per_symbol(idx_sorted_by_time, time_ms, sym, block_bars=30):
    """Keep a row only if its symbol has no position from an earlier kept row within the next `block_bars` candles."""
    free = {}
    keep = []
    for i in idx_sorted_by_time:
        s, t = int(sym[i]), int(time_ms[i])
        if t >= free.get(s, -1):
            keep.append(i)
            free[s] = t + (block_bars + 1) * H4
    return np.array(keep, dtype=np.int64)


# ------------------------------------------------------------------------------------------- walk-forward
def folds(time_ms, first_test_ms, fold_days=90):
    end = int(time_ms.max())
    start = first_test_ms
    out = []
    while start <= end:
        stop = start + fold_days * 86_400_000
        out.append((start, stop))
        start = stop
    return out
