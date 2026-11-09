"""Gates for agents: offline on the labelled evaluation set and the policy suite, then shadow on mirrored
production messages with the tools in dry-run mode. Same shape as the model gates; different evidence."""

from __future__ import annotations

import numpy as np

from paved import stats
from paved.contract import Workload
from paved.cost import conversation_cost
from paved.gates.common import Check, GateResult, at_most
from paved.ports import EvalItem
from paved.settings import settings


def score_item(item: EvalItem, result: dict) -> dict:
    claims = result.get("claims", {})
    fact_error = any(str(claims.get(k)) != str(v) for k, v in item.expected_facts.items() if k in claims)
    right = result["intent"] == item.intent and result["tool"] == item.expected_tool and not result["tool_error"]
    return {"correct": bool(right and not fact_error), "fact_error": fact_error, "has_facts": bool(item.expected_facts)}


def policy_violation(item: EvalItem, result: dict) -> bool:
    """An action the policy reserves for a person, taken by the agent alone."""
    return result["tool"] in item.forbidden_tools


def _run(agent, items: list[EvalItem]) -> list[dict]:
    return [agent.handle(i.inquiry_id, i.text) for i in items]


def offline(workload: Workload, env, champion_version, candidate_version) -> GateResult:
    g = settings()["gates"]["agent"]
    res = GateResult("offline")
    items = env.eval_set()
    champ = _run(env.make_agent(champion_version, dry_run=True), items)
    cand = _run(env.make_agent(candidate_version, dry_run=True), items)
    sc = [score_item(i, r) for i, r in zip(items, champ)]
    sn = [score_item(i, r) for i, r in zip(items, cand)]
    a = np.array([s["correct"] for s in sc], float)
    b = np.array([s["correct"] for s in sn], float)
    diff, lo, _ = stats.paired_bootstrap_diff(a, b, settings()["gates"]["model"]["bootstrap_resamples"])
    margin = workload.gate("non_inferiority_pp")
    res.checks.append(
        Check(
            "task_success_vs_champion",
            lo,
            -margin,
            lo >= -margin,
            f"task success changed {diff:+.1%} (lower 95% {lo:+.1%}, floor {-margin:+.1%})",
        )
    )
    res.info["task_success"] = {"champion": float(a.mean()), "candidate": float(b.mean())}

    worst = None
    res.info["slices"] = {}
    for col in g["slice_columns"]:
        values = sorted({getattr(i, col) for i in items})
        for v in values:
            idx = [k for k, i in enumerate(items) if getattr(i, col) == v]
            d = b[idx] - a[idx]
            upper = d.mean() + 1.28 * d.std(ddof=1) / np.sqrt(len(idx)) if len(idx) > 1 else 1.0
            res.info["slices"][f"{col}={v}"] = {"n": len(idx), "change": float(d.mean()), "upper": float(upper)}
            if len(idx) < g["slice_min_items"]:
                continue
            if worst is None or upper < worst[0]:
                worst = (upper, f"{col}={v}", len(idx), d.mean())
    if worst is not None:
        floor = -g["slice_non_inferiority_pp"]
        res.checks.append(
            Check(
                "worst_slice",
                worst[0],
                floor,
                worst[0] >= floor,
                f"task success on {worst[1]} (n={worst[2]}) changed {worst[3]:+.1%}",
            )
        )

    fa = np.array([s["fact_error"] for s in sc if s["has_facts"]], float)
    fb = np.array([s["fact_error"] for s in sn if s["has_facts"]], float)
    rate = fb.mean() if len(fb) else 0.0
    res.checks.append(
        at_most("fact_error_rate", rate, workload.gate("max_fact_error_rate"), "replies contradicting the KB")
    )
    if len(fb):
        _, _, hi = stats.paired_bootstrap_diff(fa, fb, settings()["gates"]["model"]["bootstrap_resamples"])
        res.checks.append(at_most("fact_errors_vs_champion", hi, 0.01, "extra fact errors vs champion (upper 95%)"))

    suite = env.policy_suite()
    pr = _run(env.make_agent(candidate_version, dry_run=True), suite)
    viol = sum(policy_violation(i, r) for i, r in zip(suite, pr))
    res.checks.append(
        at_most(
            "policy_violations",
            viol,
            g["policy_violations_allowed"],
            f"policy suite ({len(suite)} cases): actions taken without a person",
        )
    )
    res.info["policy_suite_handover_rate"] = float(np.mean([r["tool"] == "escalate" for r in pr]))

    cost_a = np.mean([conversation_cost(r) for r in champ])
    cost_b = np.mean([conversation_cost(r) for r in cand])
    res.checks.append(
        at_most("cost_vs_champion", cost_b / cost_a - 1, g["max_cost_increase_rel"], "cost per conversation change")
    )
    res.info["cost_per_conversation_usd"] = {"champion": float(cost_a), "candidate": float(cost_b)}
    p95 = float(np.percentile([r["latency_ms"] for r in cand], 95))
    res.checks.append(at_most("p95_latency_ms", p95, workload.gate("p95_latency_slo_ms"), "p95 latency ms"))
    return res


def shadow(workload: Workload, champ_results: list[dict], cand_results: list[dict]) -> GateResult:
    g = settings()["gates"]["agent"]
    res = GateResult("shadow")
    err = float(np.mean([r["tool_error"] for r in cand_results]))
    res.checks.append(at_most("tool_error_rate", err, g["max_tool_error_rate"], "tool calls rejected by the API"))
    p95 = float(np.percentile([r["latency_ms"] for r in cand_results], 95))
    res.checks.append(at_most("p95_latency_ms", p95, workload.gate("p95_latency_slo_ms"), "p95 latency ms"))
    ca = np.mean([conversation_cost(r) for r in champ_results])
    cb = np.mean([conversation_cost(r) for r in cand_results])
    res.checks.append(
        at_most("cost_vs_champion", cb / ca - 1, g["max_cost_increase_rel"], "cost per conversation change")
    )
    agree = float(np.mean([a["intent"] == b["intent"] for a, b in zip(champ_results, cand_results)]))
    res.info["intent_agreement_with_champion"] = agree
    return res
