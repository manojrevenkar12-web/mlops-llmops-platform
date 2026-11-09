"""Candidate releases, as data scientists and engineers actually produce them: some better, some neutral, some
broken in ways that are easy to miss. Magnitudes are drawn per seed, so some land near the line between good and
bad. Whether a release *is* good is decided by the world's truth, not by its kind."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from paved_workloads.cs_agent import AgentVersion
from paved_workloads.pricing import TrainSpec

PRICING_KINDS = [
    "better_model",
    "retrain_fresh",
    "smaller_model",
    "stale_data",
    "leaky_feature",
    "stale_partition",
    "heavy_ensemble",
    "reweighted",
    "unit_bug",
    "schema_rename",
]
AGENT_KINDS = [
    "prompt_improvement",
    "cheaper_model",
    "enable_caching",
    "guard_removed",
    "stale_kb",
    "rare_intent_regression",
    "slow_reasoning",
    "cost_blowup",
    "tool_schema_drift",
    "language_regression",
]

CHAMPION_SPEC = TrainSpec()
CHAMPION_AGENT = AgentVersion(prompt_caching=False)


@dataclass(frozen=True)
class Scenario:
    id: str
    seed: int
    workload: str  # pricing-conversion or cs-email-agent
    kind: str
    candidate: TrainSpec | AgentVersion
    note: str


def pricing(seed: int, kind: str) -> Scenario:
    r = np.random.default_rng([seed, PRICING_KINDS.index(kind)])
    c = CHAMPION_SPEC
    if kind == "better_model":
        spec = replace(c, train_from=int(r.integers(-160, -90)), extra_features=["lead_x_airport"], seed=seed)
        note = f"longer history from day {spec.train_from}, lead-time × airport feature"
    elif kind == "retrain_fresh":
        spec, note = replace(c, seed=seed + 1), "weekly retrain on the latest window"
    elif kind == "smaller_model":
        spec = replace(c, n_estimators=int(r.integers(80, 170)))
        note = f"{spec.n_estimators} trees instead of {c.n_estimators} to cut serving cost"
    elif kind == "stale_data":
        back = int(r.integers(60, 240))
        spec, note = (
            replace(c, train_from=c.train_from - back, train_to=c.train_to - back),
            f"trained on a snapshot {back} days old",
        )
    elif kind == "leaky_feature":
        spec, note = (
            replace(c, extra_features=["upgrade_after_booking"]),
            "adds upgrade_after_booking (written after the booking)",
        )
    elif kind == "stale_partition":
        by = int(r.integers(90, 260))
        spec, note = (
            replace(c, stale_partition=("station_type", "airport"), stale_by=by),
            f"airport partition backfilled from {by} days ago",
        )
    elif kind == "heavy_ensemble":
        n = int(r.integers(220, 600))
        spec, note = replace(c, n_estimators=n, num_leaves=127), f"{n} trees × 127 leaves for a little more accuracy"
    elif kind == "reweighted":
        pw = float(np.round(r.uniform(0.15, 1.4), 2))
        spec, note = (
            replace(c, booked_weight_power=pw),
            f"booked rows weighted by multiplier^{pw} to favour high-value bookings",
        )
    elif kind == "unit_bug":
        spec, note = (
            replace(c, online_competitor_scale=100.0),
            "online feature pipeline sends competitor index in percent",
        )
    elif kind == "schema_rename":
        spec, note = replace(c, online_class_upper=True), "upstream system now sends car classes in upper case"
    else:
        raise ValueError(kind)
    return Scenario(f"{seed}-pricing-{kind}", seed, "pricing-conversion", kind, spec, note)


def agent(seed: int, kind: str) -> Scenario:
    r = np.random.default_rng([seed, 100 + AGENT_KINDS.index(kind)])
    c = CHAMPION_AGENT
    if kind == "prompt_improvement":
        v, note = replace(c, prompt_version="v5"), "prompt v5: clearer intent definitions"
    elif kind == "cheaper_model":
        prompt = "v5" if r.random() < 0.5 else "v4"
        v = replace(c, model_id="anthropic.claude-haiku-4-5", prompt_version=prompt)
        note = f"Claude Haiku 4.5 instead of Sonnet 4.5, prompt {prompt}"
    elif kind == "enable_caching":
        v, note = replace(c, prompt_caching=True), "prompt caching on the system prompt and tools"
    elif kind == "guard_removed":
        v, note = replace(c, policy_guard=False), "policy guard node removed to save a step"
    elif kind == "stale_kb":
        v, note = replace(c, kb_version="v3"), "deployment still points at knowledge-base index v3"
    elif kind == "rare_intent_regression":
        v, note = replace(c, prompt_version="v5-terse"), "shorter prompt v5-terse"
    elif kind == "slow_reasoning":
        v, note = replace(c, thinking=True), "extended thinking on every step"
    elif kind == "cost_blowup":
        v, note = replace(c, context="full_history"), "full customer history in every prompt"
    elif kind == "tool_schema_drift":
        v, note = replace(c, tools_version="v1"), "tool definitions built against reservation API v1"
    elif kind == "language_regression":
        v, note = replace(c, prompt_version="v5-en-only"), "prompt v5 rewritten in English only"
    else:
        raise ValueError(kind)
    return Scenario(f"{seed}-agent-{kind}", seed, "cs-email-agent", kind, v, note)


def scenarios(seeds: list[int], exclude: list[str]) -> list[Scenario]:
    out = []
    for s in seeds:
        out += [pricing(s, k) for k in PRICING_KINDS if k not in exclude]
        out += [agent(s, k) for k in AGENT_KINDS if k not in exclude]
    return out
