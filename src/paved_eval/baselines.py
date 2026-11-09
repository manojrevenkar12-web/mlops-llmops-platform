"""How releases went before the platform, for comparison only.

- `offline_only`: the data scientist compares the offline metric with the champion and deploys to 100%.
- `fixed_canary`: 10% of traffic for a fixed number of requests, then a two-sided z-test on the primary metric;
  roll back if significantly worse, else ship. No shadow, no slices, no guardrails, no policy suite.
"""

from __future__ import annotations

import math

import numpy as np

from paved import stats
from paved.gates.agent import score_item
from paved.settings import settings


def offline_only(workload, env, champion, candidate) -> dict:
    if workload.kind == "model":
        h = env.holdout()
        y = h[workload.evaluation.label].to_numpy()
        a = stats.log_loss_per_row(y, champion.predict(champion.features(h, online=False))).mean()
        b = stats.log_loss_per_row(y, candidate.predict(candidate.features(h, online=False))).mean()
        ok = b <= a
    else:
        items = env.eval_set()
        ra = [env.make_agent(champion, True).handle(i.inquiry_id, i.text) for i in items]
        rb = [env.make_agent(candidate, True).handle(i.inquiry_id, i.text) for i in items]
        a = np.mean([score_item(i, r)["correct"] for i, r in zip(items, ra)])
        b = np.mean([score_item(i, r)["correct"] for i, r in zip(items, rb)])
        ok = b >= a
    return {"decision": "promoted" if ok else "blocked", "exposure": 0, "hours": 1.0}


def fixed_canary(workload, env, champion, candidate) -> dict:
    b = settings()["baselines"]
    c = settings()["canary"]
    share = b["fixed_canary_share"]
    if workload.kind == "model":
        cand, champ = env.canary_step(champion, candidate, share, b["fixed_canary_requests"])
        yc, yk = cand.value, champ.value
        hours = c["model_step_hours"]
    else:
        cand, champ = env.canary_step(champion, candidate, share, b["fixed_canary_agent_requests"])
        yc, yk = cand.resolved.astype(float), champ.resolved.astype(float)
        hours = c["agent_step_hours"]
    diff = yc.mean() - yk.mean()
    se = math.sqrt(yc.var(ddof=1) / len(yc) + yk.var(ddof=1) / len(yk))
    worse = diff / se < -stats.Z95
    return {"decision": "rolled_back" if worse else "promoted", "exposure": len(yc), "hours": float(hours)}
