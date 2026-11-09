"""The canary: traffic moves in steps, and after every step an always-valid confidence sequence on the primary
metric decides whether to roll back, go on, or promote. Guardrails can stop it at any step.

A fixed-horizon test checked after every step would find "significant" harm in a good release far too often.
The confidence sequence below holds at every look, so looking early is free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from paved import stats
from paved.contract import Workload
from paved.ports import AgentArm, ModelArm
from paved.settings import settings


@dataclass
class StepDecision:
    step: int
    share: float
    n_candidate: int
    n_champion: int
    effect: float  # candidate minus champion, in the primary metric's unit
    lower: float
    upper: float
    margin: float
    decision: str  # "continue", "promote", "rollback", "hold"
    reason: str
    guardrails: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _interval(y_c: np.ndarray, y_k: np.ndarray, alpha: float, tau: float) -> tuple[float, float, float]:
    diff = y_c.mean() - y_k.mean()
    var = y_c.var(ddof=1) / len(y_c) + y_k.var(ddof=1) / len(y_k)
    r = stats.cs_radius(var, alpha, tau)
    return float(diff), float(diff - r), float(diff + r)


def _decide(step: int, last: bool, diff: float, lo: float, hi: float, margin: float) -> tuple[str, str]:
    if hi < -margin:
        return "rollback", f"worse than the champion beyond the margin ({hi:+.4g} < {-margin:+.4g})"
    if last:
        if lo > -margin:
            return "promote", f"non-inferior at the last step (lower bound {lo:+.4g} > {-margin:+.4g})"
        return "hold", f"not shown non-inferior after the last step (lower bound {lo:+.4g})"
    return "continue", f"effect {diff:+.4g}, interval [{lo:+.4g}, {hi:+.4g}]"


class ModelCanary:
    """Primary metric: business value per request (revenue per offer for pricing), variance-reduced with the
    champion's expected value for the same request (CUPED). Guardrails: outcome rate, latency, forecast quality."""

    def __init__(self, workload: Workload):
        self.w = workload
        c = settings()["canary"]
        self.steps, self.sizes, self.alpha = c["model_steps"], c["model_requests_per_step"], c["alpha"]
        self.c = c
        self.arms: list[ModelArm] = []

    def evaluate(
        self, step: int, cand: ModelArm, champ: ModelArm, seen: list[tuple[ModelArm, ModelArm]]
    ) -> StepDecision:
        cs = [s[0] for s in seen] + [cand]
        ks = [s[1] for s in seen] + [champ]
        rc, rk = np.concatenate([a.value for a in cs]), np.concatenate([a.value for a in ks])
        xc, xk = np.concatenate([a.covariate for a in cs]), np.concatenate([a.covariate for a in ks])
        x = np.concatenate([xc, xk])
        y = np.concatenate([rc, rk])
        theta = np.cov(y, x)[0, 1] / x.var(ddof=1)
        yc, yk = rc - theta * (xc - x.mean()), rk - theta * (xk - x.mean())
        margin = self.c["model_margin_rel"] * rk.mean()
        diff, lo, hi = _interval(yc, yk, self.alpha, self.c["mixture_scale"] * margin)
        last = step == len(self.steps) - 1
        decision, reason = _decide(step, last, diff, lo, hi, margin)

        guard = {}
        bc, bk = np.concatenate([a.outcome for a in cs]), np.concatenate([a.outcome for a in ks])
        bdiff, _, bhi = _interval(
            bc.astype(float), bk.astype(float), self.alpha, self.c["model_conversion_drop_rel"] * bk.mean()
        )
        guard["conversion_change"] = bdiff / bk.mean()
        if bhi < -self.c["model_conversion_drop_rel"] * bk.mean():
            decision, reason = "rollback", f"conversion fell {bdiff / bk.mean():+.1%}"
        lat = float(np.percentile(np.concatenate([a.latency_ms for a in cs]), 95))
        guard["p95_latency_ms"] = lat
        if lat > self.w.gate("p95_latency_slo_ms"):
            decision, reason = "rollback", f"p95 latency {lat:.1f} ms above the SLO"
        # The conversion forecast feeds fleet planning: the candidate must not forecast worse than the champion.
        pc, pk = np.concatenate([a.predicted for a in cs]), np.concatenate([a.predicted for a in ks])
        lo_c, hi_c = stats.wilson(int(bc.sum()), len(bc))
        gap_c = max(0.0, pc.mean() - hi_c, lo_c - pc.mean()) / bc.mean()
        gap_k = abs(pk.mean() - bk.mean()) / bk.mean()
        guard["forecast_gap_candidate"], guard["forecast_gap_champion"] = gap_c, gap_k
        if gap_c > gap_k + 0.05:
            decision, reason = "rollback", f"conversion forecast off by {gap_c:.1%} (champion {gap_k:.1%})"
        return StepDecision(step, self.steps[step], len(rc), len(rk), diff, lo, hi, margin, decision, reason, guard)


class AgentCanary:
    """Primary metric: resolution (no recontact within three days). Guardrails: audited policy violations,
    escalations, cost per conversation, latency and tool errors."""

    def __init__(self, workload: Workload):
        self.w = workload
        c = settings()["canary"]
        self.steps, self.sizes, self.alpha = c["agent_steps"], c["agent_requests_per_step"], c["alpha"]
        self.c = c
        self.g = settings()["gates"]["agent"]

    def evaluate(
        self, step: int, cand: AgentArm, champ: AgentArm, seen: list[tuple[AgentArm, AgentArm]]
    ) -> StepDecision:
        cs = [s[0] for s in seen] + [cand]
        ks = [s[1] for s in seen] + [champ]
        cat = lambda arms, f: np.concatenate([getattr(a, f) for a in arms])
        yc, yk = cat(cs, "resolved").astype(float), cat(ks, "resolved").astype(float)
        margin = self.c["agent_margin_pp"]
        diff, lo, hi = _interval(yc, yk, self.alpha, self.c["mixture_scale"] * margin)
        last = step == len(self.steps) - 1
        decision, reason = _decide(step, last, diff, lo, hi, margin)

        guard = {}
        audited = cat(cs, "audited")
        viol = int(cat(cs, "violation")[audited].sum())
        guard["audited"], guard["violations"] = int(audited.sum()), viol
        if audited.sum() and viol / audited.sum() > self.c["agent_max_violation_rate"]:
            decision, reason = "rollback", f"{viol} policy violation(s) in {int(audited.sum())} audited conversations"
        ec, ek = cat(cs, "escalated").astype(float), cat(ks, "escalated").astype(float)
        ediff, elo, _ = _interval(ec, ek, self.alpha, 0.02)
        guard["escalation_change_pp"] = ediff
        if elo > self.c["agent_max_escalation_increase_pp"]:
            decision, reason = "rollback", f"escalations up {ediff:+.1%}"
        cost_c, cost_k = cat(cs, "cost_usd").mean(), cat(ks, "cost_usd").mean()
        guard["cost_change"] = cost_c / cost_k - 1
        if cost_c / cost_k - 1 > self.g["max_cost_increase_rel"]:
            decision, reason = "rollback", f"cost per conversation up {cost_c / cost_k - 1:+.0%}"
        lat = float(np.percentile(cat(cs, "latency_ms"), 95))
        guard["p95_latency_ms"] = lat
        if lat > self.w.gate("p95_latency_slo_ms"):
            decision, reason = "rollback", f"p95 latency {lat:.0f} ms above the SLO"
        terr = float(cat(cs, "tool_error").mean())
        guard["tool_error_rate"] = terr
        if terr > self.g["max_tool_error_rate"]:
            decision, reason = "rollback", f"tool error rate {terr:.1%}"
        return StepDecision(step, self.steps[step], len(yc), len(yk), diff, lo, hi, margin, decision, reason, guard)
