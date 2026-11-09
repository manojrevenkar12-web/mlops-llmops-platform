from dataclasses import replace

from paved.gates import agent as gates
from paved_eval.scenarios import CHAMPION_AGENT as CHAMP


def test_the_champion_against_itself_passes(agent_workload, service_world):
    r = gates.offline(agent_workload, service_world, CHAMP, CHAMP)
    assert r.passed, r.summary()


def test_removing_the_policy_guard_is_caught_by_the_policy_suite(agent_workload, service_world):
    r = gates.offline(agent_workload, service_world, CHAMP, replace(CHAMP, policy_guard=False))
    v = next(c for c in r.checks if c.name == "policy_violations")
    assert not v.passed and v.value > 0


def test_a_stale_knowledge_base_is_caught_by_the_fact_check(agent_workload, service_world):
    r = gates.offline(agent_workload, service_world, CHAMP, replace(CHAMP, kb_version="v3"))
    assert "fact_error_rate" in [c.name for c in r.failures()]


def test_a_language_regression_shows_in_the_slices(agent_workload, service_world):
    r = gates.offline(agent_workload, service_world, CHAMP, replace(CHAMP, prompt_version="v5-en-only"))
    assert "worst_slice" in [c.name for c in r.failures()]
    slices = r.info["slices"]
    assert all(slices[f"language={x}"]["change"] < -0.08 for x in ("fr", "es", "it"))
    assert slices["language=en"]["change"] > -0.02


def test_cost_and_latency_regressions_fail(agent_workload, service_world):
    r = gates.offline(agent_workload, service_world, CHAMP, replace(CHAMP, context="full_history"))
    assert "cost_vs_champion" in [c.name for c in r.failures()]
    r = gates.offline(agent_workload, service_world, CHAMP, replace(CHAMP, thinking=True))
    assert "p95_latency_ms" in [c.name for c in r.failures()]


def test_shadow_catches_tool_schema_drift(agent_workload, service_world):
    champ, cand = service_world.shadow(CHAMP, replace(CHAMP, tools_version="v1"), 300)
    r = gates.shadow(agent_workload, champ, cand)
    assert "tool_error_rate" in [c.name for c in r.failures()]


def test_the_agent_graph_has_the_guard_node_only_when_enabled(service_world):
    with_guard = service_world.make_agent(CHAMP, dry_run=True)
    without = service_world.make_agent(replace(CHAMP, policy_guard=False), dry_run=True)
    assert "policy_guard" in with_guard.graph.get_graph().nodes
    assert "policy_guard" not in without.graph.get_graph().nodes
