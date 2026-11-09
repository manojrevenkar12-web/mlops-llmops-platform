"""A new team gets onto the platform with a contract and its own code, and no platform change."""

import numpy as np
import yaml

from paved.cli import main
from paved.contract import load
from paved.gates import model as model_gates
from paved.settings import ROOT
from paved_workloads import damage


def test_a_third_workload_runs_the_offline_gate_with_no_platform_change():
    w = load(ROOT / "workloads" / "damage-cost" / "workload.yaml")
    train = w.load_entrypoint()
    data = damage.synthetic_reports(np.random.default_rng(0), 30_000, -200, 0)
    champ = train(data, damage.DamageSpec(n_estimators=120))
    cand = train(data, damage.DamageSpec(n_estimators=150))
    hold = data[data["day"] >= -14]
    r = model_gates.offline(w, champ, cand, hold)
    assert r.info["loss"]["metric"] == "rmse" and r.passed, r.summary()
    worse = train(data, damage.DamageSpec(n_estimators=5))
    assert not model_gates.offline(w, champ, worse, hold).passed


def test_paved_init_scaffolds_a_valid_workload_and_its_ci(tmp_path, capsys):
    assert (
        main(
            [
                "init",
                "--kind",
                "agent",
                "--name",
                "station-faq",
                "--team",
                "branch-ops",
                "--owner",
                "ops@example.com",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    wl = tmp_path / "workloads" / "station-faq" / "workload.yaml"
    assert load(wl).kind == "agent"
    ci = yaml.safe_load((tmp_path / ".github" / "workflows" / "release-station-faq.yml").read_text())
    assert "release" in ci["jobs"]
    assert main(["validate", str(wl)]) == 0
    assert "valid" in capsys.readouterr().out


def test_validate_reports_a_broken_contract(tmp_path, capsys):
    bad = tmp_path / "w.yaml"
    bad.write_text("name: X\nkind: model\n")
    assert main(["validate", str(bad)]) == 1
