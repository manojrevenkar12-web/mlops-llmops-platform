"""The release path. One state machine for models and agents:

    contract → offline → shadow → canary step 1 … n → promoted | blocked | rolled back | held

Every step is an event with its evidence and a reason. A step that already ran is not run again, so a pipeline
that dies mid-canary resumes where it stopped. Traffic moves only through the router port, which on AWS sets
SageMaker production-variant weights or the AgentCore endpoint's version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from paved.contract import Workload
from paved.events import EventLog
from paved.gates import agent as agent_gates
from paved.gates import model as model_gates
from paved.gates.canary import AgentCanary, ModelCanary
from paved.gates.common import Check, GateResult
from paved.settings import settings


class Router(Protocol):
    def shift(self, release_id: str, share: float) -> None: ...
    def rollback(self, release_id: str) -> None: ...
    def promote(self, release_id: str) -> None: ...


class RecordingRouter:
    """A router that only records what it was asked to do (local runs and tests)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def shift(self, release_id: str, share: float) -> None:
        self.calls.append(("shift", release_id, share))

    def rollback(self, release_id: str) -> None:
        self.calls.append(("rollback", release_id, 0.0))

    def promote(self, release_id: str) -> None:
        self.calls.append(("promote", release_id, 1.0))


@dataclass
class Release:
    id: str
    workload: Workload
    champion: Any
    candidate: Any
    note: str = ""


@dataclass
class Outcome:
    release_id: str
    decision: str  # promoted, blocked, rolled_back, held
    stage: str
    reason: str
    exposure: int  # customer requests the candidate served before the decision
    hours: float  # from release start to decision
    steps: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Pipeline:
    def __init__(self, log: EventLog, router: Router | None = None):
        self.log = log
        self.router = router or RecordingRouter()
        self.cfg = settings()["canary"]

    def _gate(self, rel: Release, stage: str, fn, hours: float, clock: list[float]) -> GateResult:
        prior = self.log.get(rel.id, stage)
        if prior is not None:
            r = GateResult(stage, [Check(**c) for c in prior.payload["checks"]], prior.payload["info"])
        else:
            r = fn()
            clock[0] += hours
            self.log.append(rel.id, stage, "gate", {**r.to_dict(), "hours": clock[0]}, at=clock[0])
        return r

    def run(self, rel: Release, env) -> Outcome:
        done = self.log.get(rel.id, "decision")
        if done is not None:
            return Outcome(**done.payload)
        w = rel.workload
        clock = [0.0]
        self.log.append(
            rel.id, "start", "release", {"workload": w.name, "kind": w.kind, "team": w.team, "note": rel.note}, at=0.0
        )

        if w.kind == "model":
            hold = env.holdout()
            offline = lambda: model_gates.offline(w, rel.champion, rel.candidate, hold)
            shadow = lambda: model_gates.shadow(
                w, rel.candidate, env.shadow(rel.candidate, settings()["gates"]["model"]["shadow_requests"])
            )
            canary = ModelCanary(w)
            step_hours = self.cfg["model_step_hours"]
        else:
            offline = lambda: agent_gates.offline(w, env, rel.champion, rel.candidate)

            def shadow() -> GateResult:
                champ, cand = env.shadow(rel.champion, rel.candidate, settings()["gates"]["agent"]["shadow_requests"])
                return agent_gates.shadow(w, champ, cand)

            canary = AgentCanary(w)
            step_hours = self.cfg["agent_step_hours"]

        for stage, fn, hours in (
            ("offline", offline, self.cfg["offline_hours"]),
            ("shadow", shadow, self.cfg["shadow_hours"]),
        ):
            r = self._gate(rel, stage, fn, hours, clock)
            if not r.passed:
                return self._finish(rel, "blocked", stage, r.summary(), 0, clock[0], [])

        seen: list = []
        exposure = 0
        steps: list[dict] = []
        for i, (share, n) in enumerate(zip(canary.steps, canary.sizes)):
            key = f"canary_{i}"
            prior = self.log.get(rel.id, key)
            if prior is not None:
                # Resumed after a crash: the traffic already moved and the step's decision is in the record. Later
                # steps use the data they collect themselves, which only makes the interval wider (conservative).
                steps.append(prior.payload)
                if prior.payload["decision"] != "continue":
                    return self._finish(
                        rel,
                        *_final(prior.payload),
                        exposure + prior.payload["n_candidate"],
                        prior.payload["hours"],
                        steps,
                    )
                continue
            self.router.shift(rel.id, share)
            cand, champ = env.canary_step(rel.champion, rel.candidate, share, n)
            exposure += len(cand.latency_ms)
            d = canary.evaluate(i, cand, champ, seen)
            seen.append((cand, champ))
            clock[0] += step_hours
            payload = {**d.to_dict(), "hours": clock[0]}
            self.log.append(rel.id, key, "canary", payload, at=clock[0])
            steps.append(payload)
            if d.decision != "continue":
                decision, stage, reason = _final(payload)
                return self._finish(rel, decision, stage, reason, exposure, clock[0], steps)
        raise AssertionError("the last canary step always decides")

    def _finish(
        self, rel: Release, decision: str, stage: str, reason: str, exposure: int, hours: float, steps: list
    ) -> Outcome:
        if decision == "promoted":
            self.router.promote(rel.id)
        elif decision in ("rolled_back", "held") and steps:
            self.router.rollback(rel.id)
        out = Outcome(rel.id, decision, stage, reason, exposure, hours, steps)
        self.log.append(rel.id, "decision", "decision", out.to_dict(), at=hours)
        return out

    def override(self, release_id: str, person: str, reason: str) -> None:
        """A person may promote a held or blocked release. The platform records who and why; it never decides
        silently. Policy-violation blocks are not overridable."""
        d = self.log.get(release_id, "decision")
        if d is None or d.payload["decision"] not in ("held", "blocked"):
            raise ValueError("only a held or blocked release can be overridden")
        if "policy" in d.payload["reason"]:
            raise ValueError("a policy-violation block cannot be overridden")
        if not reason.strip() or "@" not in person:
            raise ValueError("an override needs a named person and a reason")
        self.log.append(release_id, "override", "override", {"person": person, "reason": reason})
        self.router.promote(release_id)


def _final(payload: dict) -> tuple[str, str, str]:
    mapping = {"promote": "promoted", "rollback": "rolled_back", "hold": "held"}
    return mapping[payload["decision"]], f"canary_{payload['step']}", payload["reason"]
