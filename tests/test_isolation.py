"""The platform never sees the truth: nothing under src/paved imports the simulated world or the evaluation."""

import ast

from paved.settings import ROOT

FORBIDDEN = ("paved_world", "paved_eval")


def _imports(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_the_platform_never_imports_the_world_or_the_evaluation():
    offenders = [
        (str(p.relative_to(ROOT)), m)
        for p in (ROOT / "src" / "paved").rglob("*.py")
        for m in _imports(p)
        if m.split(".")[0] in FORBIDDEN
    ]
    assert offenders == []


def test_team_code_does_not_import_the_world_either():
    offenders = [
        (str(p.relative_to(ROOT)), m)
        for p in (ROOT / "src" / "paved_workloads").rglob("*.py")
        for m in _imports(p)
        if m.split(".")[0] in FORBIDDEN
    ]
    assert offenders == []


def test_the_knowledge_base_v5_matches_what_is_true():
    from paved_workloads.cs_agent import KB
    from paved_world.service import POLICY_FACTS

    assert KB["v5"] == POLICY_FACTS
    assert KB["v3"] != POLICY_FACTS
