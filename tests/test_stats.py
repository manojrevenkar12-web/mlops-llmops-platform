import math

import numpy as np

from paved import stats


def test_wilson_matches_published_values():
    # Wilson score interval for 81/263 (Newcombe 1998, example 1): 0.2553 to 0.3662
    lo, hi = stats.wilson(81, 263)
    assert math.isclose(lo, 0.2553, abs_tol=5e-4) and math.isclose(hi, 0.3662, abs_tol=5e-4)
    assert stats.wilson(0, 0) == (0.0, 1.0)


def test_confidence_sequence_keeps_its_error_rate_under_repeated_looks():
    """Under no effect, looking after every step must not find a difference more often than alpha."""
    rng = np.random.default_rng(1)
    alpha, false_alarms, runs = 0.05, 0, 400
    for _ in range(runs):
        a = rng.normal(0, 1, 6000)
        b = rng.normal(0, 1, 6000)
        for n in range(200, 6001, 200):  # 30 looks
            diff = b[:n].mean() - a[:n].mean()
            r = stats.cs_radius(2 / n, alpha, tau=0.1)
            if abs(diff) > r:
                false_alarms += 1
                break
    assert false_alarms / runs <= alpha


def test_naive_repeated_testing_would_not_keep_it():
    """The reason for the confidence sequence: a fixed z-test checked 30 times alarms far more often."""
    rng = np.random.default_rng(2)
    alarms = 0
    for _ in range(300):
        a, b = rng.normal(0, 1, 6000), rng.normal(0, 1, 6000)
        if any(abs(b[:n].mean() - a[:n].mean()) / math.sqrt(2 / n) > stats.Z95 for n in range(200, 6001, 200)):
            alarms += 1
    assert alarms / 300 > 0.15


def test_radius_shrinks_with_evidence():
    assert stats.cs_radius(1e-2, 0.05, 0.1) > stats.cs_radius(1e-4, 0.05, 0.1) > 0


def test_paired_bootstrap_and_calibration():
    rng = np.random.default_rng(3)
    a = rng.normal(0, 1, 2000)
    d, lo, hi = stats.paired_bootstrap_diff(a, a + 0.5, 300)
    assert math.isclose(d, 0.5) and lo <= 0.5 <= hi
    p = rng.uniform(0, 1, 20000)
    y = (rng.uniform(0, 1, 20000) < p).astype(float)
    assert stats.calibration_error(y, p, 10) < 0.02
    assert stats.calibration_error(y, np.clip(p + 0.2, 0, 1), 10) > 0.1


def test_psi_is_zero_for_the_same_distribution_and_large_for_a_shift():
    rng = np.random.default_rng(4)
    x = rng.normal(0, 1, 5000)
    assert stats.psi(x, rng.normal(0, 1, 5000)) < 0.02
    assert stats.psi(x, rng.normal(1, 1, 5000)) > 0.25
    cats = np.array(["a", "b", "c"] * 1000)
    assert stats.psi(cats, np.array(["A", "B", "C"] * 1000)) > 1
