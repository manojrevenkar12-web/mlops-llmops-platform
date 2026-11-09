"""Delivery and adoption metrics, computed from the release record and nothing else.

The four delivery measures (DORA) translated to models and agents, per team:
- lead time: hours from release start to a decision;
- change failure rate: of the releases that reached customers, the share rolled back;
- exposure before rollback: customer requests a failed release served;
- self-service rate: releases decided by the path itself, without a person overriding it.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from paved.events import EventLog


def releases(log: EventLog) -> list[dict]:
    by_release: dict[str, dict] = defaultdict(dict)
    for e in log.events():
        r = by_release[e.release_id]
        if e.step == "start":
            r.update(
                release=e.release_id, team=e.payload["team"], workload=e.payload["workload"], kind=e.payload["kind"]
            )
        elif e.step == "decision":
            r.update(
                decision=e.payload["decision"],
                stage=e.payload["stage"],
                hours=e.payload["hours"],
                exposure=e.payload["exposure"],
                reason=e.payload["reason"],
            )
        elif e.step == "override":
            r["overridden_by"] = e.payload["person"]
    return [r for r in by_release.values() if "decision" in r]


def delivery_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"releases": 0}
    reached = [r for r in rows if r["stage"].startswith("canary")]
    failed = [r for r in reached if r["decision"] == "rolled_back"]
    promoted = [r for r in rows if r["decision"] == "promoted"]
    return {
        "releases": len(rows),
        "promoted": len(promoted),
        "blocked_before_customers": sum(r["decision"] == "blocked" for r in rows),
        "reached_customers": len(reached),
        "change_failure_rate": len(failed) / len(reached) if reached else 0.0,
        "median_lead_time_hours": median(r["hours"] for r in promoted) if promoted else None,
        "median_exposure_before_rollback": median(r["exposure"] for r in failed) if failed else 0,
        "self_service_rate": sum("overridden_by" not in r for r in rows) / len(rows),
    }


def by_team(log: EventLog) -> dict:
    rows = releases(log)
    teams: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        teams[r["team"]].append(r)
    return {t: delivery_metrics(rs) for t, rs in sorted(teams.items())}
