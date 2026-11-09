"""The control plane's HTTP API: workloads, releases and their evidence, delivery metrics, cost.

uvicorn paved.api:app
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError

from paved import adoption
from paved.contract import load
from paved.events import EventLog
from paved.settings import ROOT

app = FastAPI(title="paved", version="1.0.0")
EVENTS = Path(os.environ.get("PAVED_EVENTS", ROOT / "runs" / "api-events.sqlite"))


def _log() -> EventLog:
    return EventLog(EVENTS)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/workloads")
def workloads() -> list[dict]:
    out = []
    for p in sorted((ROOT / "workloads").glob("*/workload.yaml")):
        w = load(p)
        out.append(
            {
                "name": w.name,
                "kind": w.kind,
                "team": w.team,
                "owner": w.owner,
                "serving": w.serving.target,
                "budget_usd_month": w.budget_usd_month,
            }
        )
    return out


class ReleaseRequest(BaseModel):
    workload: str
    commit: str


@app.post("/releases", status_code=202)
def request_release(req: ReleaseRequest) -> dict:
    path = ROOT / "workloads" / req.workload / "workload.yaml"
    if not path.exists():
        raise HTTPException(404, f"no workload {req.workload}")
    try:
        w = load(path)
    except ValidationError as e:
        raise HTTPException(422, str(e)) from e
    release_id = f"{w.name}-{req.commit[:12]}"
    ev = _log().append(release_id, "requested", "request", {"workload": w.name, "team": w.team, "commit": req.commit})
    return {"release": release_id, "queued_at": ev.at}


@app.get("/releases/{release_id}")
def release(release_id: str) -> list[dict]:
    events = _log().events(release_id)
    if not events:
        raise HTTPException(404, "unknown release")
    return [{"step": e.step, "kind": e.kind, "payload": e.payload, "at": e.at} for e in events]


@app.get("/metrics/delivery")
def delivery() -> dict:
    return adoption.by_team(_log())


@app.get("/reports/{name}")
def report(name: str) -> dict:
    if name not in {"dev", "heldout", "cost", "dashboard"}:
        raise HTTPException(404, "unknown report")
    p = ROOT / "reports" / f"{name}.json"
    if not p.exists():
        raise HTTPException(404, "not generated yet")
    return json.loads(p.read_text())
