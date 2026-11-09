"""The release path itself, against a fake world: order of stages, idempotent steps, resume, overrides."""

import numpy as np
import pandas as pd
import pytest

from paved.events import EventLog
from paved.pipeline import Pipeline, RecordingRouter, Release
from paved.ports import ModelArm, ModelShadow


class FakeModel:
    def __init__(self, name, offset=0.0, latency=5.0, train_to=-14):
        self.name, self.offset, self.latency, self.train_to, self.complexity = name, offset, latency, train_to, 1

    def features(self, data, online):
        return data[["x"]].assign(station_type="city", car_class="economy")

    def predict(self, frame):
        return np.clip(0.3 + self.offset + 0 * frame["x"].to_numpy(), 0.01, 0.99)


class FakeWorld:
    def __init__(self, lift=0.0):
        rng = np.random.default_rng(0)
        self.h = pd.DataFrame(
            {
                "x": rng.random(4000),
                "booked": (rng.random(4000) < 0.3).astype(int),
                "station_type": "city",
                "car_class": "economy",
            }
        )
        self.lift, self.canary_calls = lift, 0

    def holdout(self):
        return self.h

    def shadow(self, cand, n):
        f = cand.features(self.h.iloc[:n], online=True)
        return ModelShadow(f, self.h.iloc[:n], np.full(n, cand.latency), 0)

    def canary_step(self, champ, cand, share, n):
        self.canary_calls += 1
        rng = np.random.default_rng(self.canary_calls)

        def arm(lift):
            cov = rng.gamma(2, 45, n)
            b = (rng.random(n) < 0.3).astype(int)
            return ModelArm(b * cov / 0.3 * (1 + lift), b, np.full(n, 0.3), cov, np.full(n, 5.0), 0)

        return arm(self.lift), arm(0.0)


def test_a_good_release_walks_every_step_and_is_promoted(pricing_workload):
    log, router = EventLog(), RecordingRouter()
    out = Pipeline(log, router).run(Release("r1", pricing_workload, FakeModel("a"), FakeModel("b")), FakeWorld())
    assert out.decision == "promoted"
    assert [e.step for e in log.events("r1")] == [
        "start",
        "offline",
        "shadow",
        "canary_0",
        "canary_1",
        "canary_2",
        "decision",
    ]
    assert [c[0] for c in router.calls] == ["shift", "shift", "shift", "promote"]
    assert log.verify()


def test_a_release_blocked_offline_never_touches_traffic(pricing_workload):
    router = RecordingRouter()
    out = Pipeline(EventLog(), router).run(
        Release("r2", pricing_workload, FakeModel("a"), FakeModel("b", train_to=0)), FakeWorld()
    )
    assert out.decision == "blocked" and out.stage == "offline" and out.exposure == 0
    assert router.calls == []


def test_a_rerun_returns_the_recorded_decision_without_running_anything(pricing_workload):
    log, world = EventLog(), FakeWorld()
    rel = Release("r3", pricing_workload, FakeModel("a"), FakeModel("b"))
    first = Pipeline(log).run(rel, world)
    calls = world.canary_calls
    again = Pipeline(log).run(rel, world)
    assert again.decision == first.decision and world.canary_calls == calls


def test_a_pipeline_that_died_mid_canary_resumes_without_repeating_steps(pricing_workload):
    log, world = EventLog(), FakeWorld()
    rel = Release("r4", pricing_workload, FakeModel("a"), FakeModel("b"))
    p = Pipeline(log)
    orig = world.canary_step

    def dies_on_second(*a):
        if world.canary_calls == 1:
            raise RuntimeError("worker lost")
        return orig(*a)

    world.canary_step = dies_on_second
    with pytest.raises(RuntimeError):
        p.run(rel, world)
    world.canary_step = orig
    out = Pipeline(log).run(rel, world)
    steps = [e.step for e in log.events("r4")]
    assert steps.count("canary_0") == 1 and steps[-1] == "decision" and out.decision in ("promoted", "held")


def test_overrides_need_a_person_and_a_reason_and_never_lift_a_policy_block(pricing_workload):
    log = EventLog()
    p = Pipeline(log)
    p.run(Release("r5", pricing_workload, FakeModel("a"), FakeModel("b", train_to=0)), FakeWorld())
    with pytest.raises(ValueError):
        p.override("r5", "someone", "")
    p.override("r5", "lead@example.com", "holdout overlap is one day, accepted by the pricing lead")
    assert log.get("r5", "override").payload["person"] == "lead@example.com"
    log.append("r6", "decision", "decision", {"decision": "blocked", "reason": "policy suite: 3 violations"})
    with pytest.raises(ValueError, match="policy"):
        p.override("r6", "lead@example.com", "please")
