"""The statistics the gates use. Small, plain and tested against known values."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

Z95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def paired_bootstrap_diff(a: np.ndarray, b: np.ndarray, resamples: int, seed: int = 0) -> tuple[float, float, float]:
    """Mean of (b - a) over paired items, with a 95% percentile bootstrap interval."""
    d = np.asarray(b, float) - np.asarray(a, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), (resamples, len(d)))
    means = d[idx].mean(axis=1)
    return float(d.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def log_loss_per_row(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def calibration_error(y: np.ndarray, p: np.ndarray, bins: int) -> float:
    """Expected calibration error over equal-count bins."""
    order = np.argsort(p)
    chunks = np.array_split(order, bins)
    n = len(p)
    return float(sum(len(c) / n * abs(y[c].mean() - p[c].mean()) for c in chunks if len(c)))


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population stability index of `actual` against `expected`, on the expected sample's deciles.

    Categorical inputs (strings or pandas categories) are compared category by category; a missing value is a
    category of its own, so values the model has never seen show up instead of disappearing.
    """
    e, a = np.asarray(expected, dtype=object), np.asarray(actual, dtype=object)
    numeric = all(isinstance(x, (int, float, np.integer, np.floating)) and x == x for x in e[:100])
    if numeric:
        ef, af = e.astype(float), a.astype(float)
        edges = np.unique(np.quantile(ef, np.linspace(0, 1, bins + 1)[1:-1]))
        ei = np.searchsorted(edges, ef, side="right")
        ai = np.searchsorted(edges, af, side="right")
        k = len(edges) + 1
        ec = np.bincount(ei, minlength=k).astype(float)
        ac = np.bincount(ai, minlength=k).astype(float)
    else:
        es, as_ = pd.Series(e).astype(str).value_counts(), pd.Series(a).astype(str).value_counts()
        keys = sorted(set(es.index) | set(as_.index))
        ec = es.reindex(keys, fill_value=0).to_numpy(float)
        ac = as_.reindex(keys, fill_value=0).to_numpy(float)
    ep = np.maximum(ec / ec.sum(), 1e-4)
    ap = np.maximum(ac / ac.sum(), 1e-4)
    return float(np.sum((ap - ep) * np.log(ap / ep)))


def cs_radius(variance: float, alpha: float, tau: float) -> float:
    """Half-width of an always-valid confidence sequence for a mean difference (normal mixture, mSPRT).

    `variance` is the variance of the current estimate; `tau` the standard deviation of the mixing prior on the
    effect. The interval holds simultaneously at every look, so the canary may check after every step and stop
    as soon as it is decided without inflating its error rate (Johari et al. 2017; Howard et al. 2021).
    """
    if variance <= 0:
        return 0.0
    t2 = tau * tau
    return math.sqrt(
        2 * variance * (variance + t2) / t2 * (math.log(1 / alpha) + 0.5 * math.log((variance + t2) / variance))
    )


def cuped(y: np.ndarray, x: np.ndarray, theta: float) -> np.ndarray:
    """Variance reduction with a pre-assignment covariate (CUPED)."""
    return y - theta * (x - x.mean())
