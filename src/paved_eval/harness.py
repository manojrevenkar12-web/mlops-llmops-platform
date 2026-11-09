"""Runs every scenario through the platform and the two baselines, and scores each decision against the truth.

This is the only code that sees both sides: it asks the world for the truth after the platform has decided.
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from paved.contract import load
from paved.events import EventLog
from paved.pipeline import Pipeline, Release
from paved.settings import ROOT, settings
from paved_eval import baselines
from paved_eval.scenarios import CHAMPION_AGENT, CHAMPION_SPEC, Scenario, scenarios
from paved_workloads.pricing import train
from paved_world.environment import PricingWorld, ServiceWorld


def workload(name: str):
    return load(ROOT / "workloads" / name / "workload.yaml")


def truth_verdict(kind: str, cand: dict, champ: dict) -> tuple[bool, list[str]]:
    c, ga, gm = settings()["canary"], settings()["gates"]["agent"], settings()["gates"]["model"]
    ev = settings()["evaluation"]
    why = []
    if kind == "model":
        rel = cand["revenue_per_offer"] / champ["revenue_per_offer"] - 1
        if rel < -c["model_margin_rel"]:
            why.append(f"revenue per offer {rel:+.1%}")
        if cand["segment_forecast_error"] > champ["segment_forecast_error"] + 0.05:
            why.append(
                f"booking forecast error {cand['segment_forecast_error']:.0%} vs {champ['segment_forecast_error']:.0%}"
            )
        if cand["p95_latency_ms"] > gm["p95_latency_slo_ms"]:
            why.append(f"p95 latency {cand['p95_latency_ms']:.0f} ms")
        for k, v in cand["segments"].items():
            if v / champ["segments"][k] - 1 < -ev["truth_segment_drop_rel"]:
                why.append(f"revenue on {k} {v / champ['segments'][k] - 1:+.1%}")
    else:
        d = cand["resolution"] - champ["resolution"]
        if d < -c["agent_margin_pp"]:
            why.append(f"resolution {d:+.1%}")
        if cand["violation_rate"] > max(champ["violation_rate"], c["agent_max_violation_rate"]):
            why.append(f"policy violations {cand['violation_rate']:.1%}")
        if cand["cost_per_conversation"] / champ["cost_per_conversation"] - 1 > ga["max_cost_increase_rel"]:
            why.append(f"cost {cand['cost_per_conversation'] / champ['cost_per_conversation'] - 1:+.0%}")
        if cand["p95_latency_ms"] > ga["p95_latency_slo_ms"]:
            why.append(f"p95 latency {cand['p95_latency_ms']:.0f} ms")
        for k, v in cand["segments"].items():
            if v - champ["segments"][k] < -ev["truth_segment_drop_pp"]:
                why.append(f"resolution on {k} {v - champ['segments'][k]:+.1%}")
    return not why, why


def _effect(kind: str, cand: dict, champ: dict) -> float:
    if kind == "model":
        return cand["revenue_per_offer"] / champ["revenue_per_offer"] - 1
    return cand["resolution"] - champ["resolution"]


def run_seed(seed: int, scs: list[Scenario], events_path: str | None = None) -> list[dict]:
    rows = []
    pw = sw = None
    champ_model = champ_truth = agent_truth = None
    log = EventLog(events_path or ":memory:")
    for sc in scs:
        t0 = time.time()
        w = workload(sc.workload)
        if w.kind == "model":
            if pw is None:
                pw = PricingWorld(seed)
                champ_model = train(pw.log, CHAMPION_SPEC)
                champ_truth = pw.truth(champ_model)
            env, champion = pw, champ_model
            candidate = train(pw.log, sc.candidate)
            truth_c, truth_k = pw.truth(candidate), champ_truth
        else:
            if sw is None:
                sw = ServiceWorld(seed)
                agent_truth = sw.truth(CHAMPION_AGENT)
            env, champion, candidate = sw, CHAMPION_AGENT, sc.candidate
            truth_c, truth_k = sw.truth(candidate), agent_truth
        out = Pipeline(log).run(Release(sc.id, w, champion, candidate, sc.note), env)
        b0 = baselines.offline_only(w, env, champion, candidate)
        b1 = baselines.fixed_canary(w, env, champion, candidate)
        good, why = truth_verdict(w.kind, truth_c, truth_k)
        gates = {
            e.step: {"passed": e.payload["passed"], "checks": e.payload["checks"], "info": e.payload["info"]}
            for e in log.events(sc.id)
            if e.kind == "gate"
        }
        rows.append(
            {
                "id": sc.id,
                "seed": seed,
                "workload": sc.workload,
                "kind": sc.kind,
                "note": sc.note,
                "truth_good": good,
                "truth_why": why,
                "true_effect": _effect(w.kind, truth_c, truth_k),
                "truth": truth_c,
                "truth_champion": truth_k,
                "platform": out.to_dict(),
                "gates": gates,
                "offline_only": b0,
                "fixed_canary": b1,
                "seconds": round(time.time() - t0, 1),
            }
        )
        print(
            f"{sc.id:42s} good={good!s:5s} platform={out.decision:11s} at {out.stage:9s} "
            f"b0={b0['decision']:8s} b1={b1['decision']:11s} {time.time() - t0:5.1f}s  {out.reason[:70]}",
            flush=True,
        )
    return rows


def run(seeds: list[int], exclude: list[str], workers: int = 2, events_dir: str | None = None) -> list[dict]:
    scs = scenarios(seeds, exclude)
    by_seed = {s: [x for x in scs if x.seed == s] for s in seeds}
    paths = {s: (str(Path(events_dir) / f"events-{s}.sqlite") if events_dir else None) for s in seeds}
    with ProcessPoolExecutor(workers) as ex:
        parts = list(ex.map(run_seed, seeds, [by_seed[s] for s in seeds], [paths[s] for s in seeds]))
    return [r for p in parts for r in p]


def summarise(rows: list[dict]) -> dict:
    out = {}
    for policy in ("platform", "offline_only", "fixed_canary"):
        good = [r for r in rows if r["truth_good"]]
        bad = [r for r in rows if not r["truth_good"]]
        shipped = lambda rs, p=policy: [r for r in rs if r[p]["decision"] == "promoted"]
        hours = sorted(r[policy]["hours"] for r in rows)
        out[policy] = {
            "releases": len(rows),
            "good": len(good),
            "bad": len(bad),
            "bad_shipped": len(shipped(bad)),
            "good_shipped": len(shipped(good)),
            "good_blocked": len(good) - len(shipped(good)),
            "bad_exposure_requests": int(
                sum(r[policy]["exposure"] for r in bad if r[policy]["decision"] != "promoted")
            ),
            "median_hours_to_decision": hours[len(hours) // 2] if hours else 0.0,
        }
    return out
