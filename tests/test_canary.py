import numpy as np

from paved.gates.canary import AgentCanary, ModelCanary
from paved.ports import AgentArm, ModelArm


def _model_arm(rng, n, lift=0.0, latency=6.0, predicted_shift=0.0):
    cov = rng.gamma(2.0, 45.0, n)
    p = np.clip(0.3 + 0.0 * cov, 0, 1)
    booked = (rng.random(n) < p).astype(int)
    value = booked * cov / 0.3 * (1 + lift)
    return ModelArm(value, booked, np.full(n, 0.3 + predicted_shift), cov, np.full(n, latency), 0)


def _run_model(w, rng, lift, **kw):
    c = ModelCanary(w)
    seen = []
    for i, n in enumerate(c.sizes):
        cand, champ = _model_arm(rng, n, lift, **kw), _model_arm(rng, n)
        d = c.evaluate(i, cand, champ, seen)
        seen.append((cand, champ))
        if d.decision != "continue":
            return d
    raise AssertionError


def test_a_clearly_worse_model_is_rolled_back_at_the_first_step(pricing_workload):
    d = _run_model(pricing_workload, np.random.default_rng(1), lift=-0.10)
    assert d.decision == "rollback" and d.step == 0


def test_an_equal_model_is_promoted_after_the_last_step(pricing_workload):
    d = _run_model(pricing_workload, np.random.default_rng(2), lift=0.0)
    assert d.decision == "promote" and d.step == 2


def test_guardrails_stop_a_model_whatever_its_revenue(pricing_workload):
    d = _run_model(pricing_workload, np.random.default_rng(3), lift=0.02, latency=80.0)
    assert d.decision == "rollback" and "latency" in d.reason
    d = _run_model(pricing_workload, np.random.default_rng(4), lift=0.02, predicted_shift=0.1)
    assert d.decision == "rollback" and "forecast" in d.reason


def _agent_arm(rng, n, res=0.82, violation=0.0, cost=0.02, latency=4000.0, tool_error=0.0):
    return AgentArm(
        rng.random(n) < res,
        rng.random(n) < 0.1,
        rng.random(n) < 0.05,
        rng.random(n) < violation,
        np.full(n, cost),
        np.full(n, latency),
        rng.random(n) < tool_error,
    )


def _run_agent(w, rng, **kw):
    c = AgentCanary(w)
    seen = []
    for i, n in enumerate(c.sizes):
        cand, champ = _agent_arm(rng, n, **kw), _agent_arm(rng, n)
        d = c.evaluate(i, cand, champ, seen)
        seen.append((cand, champ))
        if d.decision != "continue":
            return d
    raise AssertionError


def test_agent_canary_decisions(agent_workload):
    assert _run_agent(agent_workload, np.random.default_rng(5)).decision == "promote"
    assert _run_agent(agent_workload, np.random.default_rng(6), res=0.70).decision == "rollback"
    d = _run_agent(agent_workload, np.random.default_rng(7), violation=0.05, res=0.85)
    assert d.decision == "rollback" and "policy" in d.reason
    d = _run_agent(agent_workload, np.random.default_rng(8), cost=0.05)
    assert d.decision == "rollback" and "cost" in d.reason
