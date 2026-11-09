"""Gates for classical models: offline against the champion, then shadow on mirrored production requests.

A model on the platform implements `features(data, online)`, `predict(features)`, `train_to` and `complexity`;
its contract names the label, the metric and the slices. Nothing here knows what the model is for.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from paved import stats
from paved.contract import Workload
from paved.gates.common import Check, GateResult, at_most
from paved.ports import ModelShadow
from paved.settings import settings


def _loss(metric: str, y: np.ndarray, p: np.ndarray) -> np.ndarray:
    return stats.log_loss_per_row(y, p) if metric == "logloss" else (y - p) ** 2


def offline(workload: Workload, champion, candidate, holdout: pd.DataFrame) -> GateResult:
    g = settings()["gates"]["model"]
    ev = workload.evaluation
    assert ev is not None
    hold_days = settings()["platform"]["holdout_days"]
    res = GateResult("offline")
    res.checks.append(at_most("holdout_untouched", candidate.train_to, -hold_days, "training ends on day"))

    y = holdout[ev.label].to_numpy()
    p_champ = champion.predict(champion.features(holdout, online=False))
    p_cand = candidate.predict(candidate.features(holdout, online=False))
    l_champ, l_cand = _loss(ev.metric, y, p_champ), _loss(ev.metric, y, p_cand)
    base = l_champ.mean()
    diff, _, hi = stats.paired_bootstrap_diff(l_champ, l_cand, g["bootstrap_resamples"])
    margin = workload.gate("non_inferiority_rel")
    res.checks.append(at_most("loss_vs_champion", hi / base, margin, f"{ev.metric} change (upper 95%)"))
    res.info["loss"] = {
        "metric": ev.metric,
        "champion": float(base),
        "candidate": float(l_cand.mean()),
        "rel_change": diff / base,
    }

    worst = None
    for col in ev.slices:
        for value, idx in holdout.groupby(col, observed=True).indices.items():
            if len(idx) < g["slice_min_rows"]:
                continue
            d = l_cand[idx] - l_champ[idx]
            lower = (d.mean() - 1.28 * d.std(ddof=1) / np.sqrt(len(idx))) / l_champ[idx].mean()
            if worst is None or lower > worst[0]:
                worst = (lower, f"{col}={value}", len(idx))
    if worst is not None:
        ok = worst[0] <= g["slice_non_inferiority_rel"]
        res.checks.append(
            Check(
                "worst_slice",
                worst[0],
                g["slice_non_inferiority_rel"],
                ok,
                f"{ev.metric} on {worst[1]} (n={worst[2]}) worse by {worst[0]:+.1%} at least",
            )
        )
    if ev.metric == "logloss":
        # Relative to the champion: drift moves both, and an absolute bar would block every release in a drift.
        ece_c = stats.calibration_error(y, p_cand, g["calibration_bins"])
        ece_k = stats.calibration_error(y, p_champ, g["calibration_bins"])
        res.checks.append(
            at_most(
                "calibration_vs_champion", ece_c - ece_k, g["max_calibration_increase"], "calibration error increase"
            )
        )
        res.info["calibration_error"] = {"champion": ece_k, "candidate": ece_c}
    return res


def shadow(workload: Workload, candidate, obs: ModelShadow) -> GateResult:
    g = settings()["gates"]["model"]
    ev = workload.evaluation
    assert ev is not None
    res = GateResult("shadow")
    # Online/offline parity: the training pipeline, replayed on the very requests the endpoint served, must
    # produce the features the endpoint received. Catches leaks, unit changes and renamed categories exactly.
    offline_view = candidate.features(obs.logged, online=False)
    mismatch = {}
    for col in offline_view.columns:
        if col in ev.skew_exclude:
            continue
        a, b = offline_view[col].to_numpy(), obs.served_features[col].to_numpy()
        if a.dtype.kind in "fiub" and b.dtype.kind in "fiub":
            diff = ~np.isclose(a.astype(float), b.astype(float), rtol=1e-6, atol=1e-9)
        else:
            diff = pd.Series(a).astype(str).to_numpy() != pd.Series(b).astype(str).to_numpy()
        mismatch[col] = float(diff.mean())
    worst = max(mismatch, key=mismatch.get)
    res.checks.append(
        Check(
            "online_offline_parity",
            mismatch[worst],
            g["max_feature_mismatch"],
            mismatch[worst] <= g["max_feature_mismatch"],
            f"feature {worst} as served differs from the training pipeline on {mismatch[worst]:.1%} of requests",
        )
    )
    res.info["feature_mismatch"] = mismatch
    p95 = float(np.percentile(obs.latency_ms, 95))
    res.checks.append(at_most("p95_latency_ms", p95, workload.gate("p95_latency_slo_ms"), "p95 latency ms"))
    rate = obs.errors / max(1, len(obs.latency_ms))
    res.checks.append(at_most("error_rate", rate, g["max_error_rate"], "error rate"))
    return res
