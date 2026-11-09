"""The `paved` command line: what a data scientist or ML engineer types.

paved init --kind model --name churn-score --team customer-analytics --owner me@example.com
paved validate workloads/churn-score/workload.yaml
paved status runs/dev/events-101.sqlite [--release ID]
paved metrics runs/dev/events-101.sqlite
paved override runs/... --release ID --person me@example.com --reason "..."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from paved import adoption
from paved.contract import load
from paved.events import EventLog
from paved.pipeline import Pipeline
from paved.scaffold import init


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="paved")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--kind", choices=["model", "agent"], required=True)
    i.add_argument("--name", required=True)
    i.add_argument("--team", required=True)
    i.add_argument("--owner", required=True)
    i.add_argument("--root", default=".")
    v = sub.add_parser("validate")
    v.add_argument("path")
    s = sub.add_parser("status")
    s.add_argument("events")
    s.add_argument("--release")
    m = sub.add_parser("metrics")
    m.add_argument("events")
    o = sub.add_parser("override")
    o.add_argument("events")
    o.add_argument("--release", required=True)
    o.add_argument("--person", required=True)
    o.add_argument("--reason", required=True)
    a = p.parse_args(argv)

    if a.cmd == "init":
        for f in init(Path(a.root), a.name, a.kind, a.team, a.owner):
            print(f"wrote {f}")
    elif a.cmd == "validate":
        try:
            w = load(a.path)
        except ValidationError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"{w.name}: {w.kind} owned by {w.team} ({w.owner}), served on {w.serving.target}: valid")
    elif a.cmd == "status":
        log = EventLog(a.events)
        for e in log.events(a.release):
            p_ = e.payload
            line = p_.get("reason") or p_.get("stage") or p_.get("workload", "")
            if e.kind == "gate":
                line = "passed" if p_["passed"] else "; ".join(c["reason"] for c in p_["checks"] if not c["passed"])
            print(f"{e.release_id:40s} {e.step:10s} {line}")
    elif a.cmd == "metrics":
        print(json.dumps(adoption.by_team(EventLog(a.events)), indent=1))
    elif a.cmd == "override":
        Pipeline(EventLog(a.events)).override(a.release, a.person, a.reason)
        print(f"{a.release}: promoted by {a.person}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
