import pytest
import yaml
from pydantic import ValidationError

from paved.contract import Workload, load
from paved.settings import ROOT


def _raw(name):
    return yaml.safe_load((ROOT / "workloads" / name / "workload.yaml").read_text())


@pytest.mark.parametrize("name", ["pricing-conversion", "cs-email-agent", "damage-cost"])
def test_every_workload_in_the_repo_validates(name):
    load(ROOT / "workloads" / name / "workload.yaml")


def test_an_agent_must_run_on_agentcore_and_a_model_on_sagemaker():
    raw = _raw("cs-email-agent")
    raw["serving"]["target"] = "sagemaker-realtime"
    with pytest.raises(ValidationError, match="AgentCore"):
        Workload.model_validate(raw)
    raw = _raw("pricing-conversion")
    raw["serving"]["target"] = "bedrock-agentcore"
    with pytest.raises(ValidationError, match="SageMaker"):
        Workload.model_validate(raw)


def test_floors_are_never_lowered():
    raw = _raw("pricing-conversion")
    raw["gates"] = {"p95_latency_slo_ms": 500}
    with pytest.raises(ValidationError, match="tightened"):
        Workload.model_validate(raw)
    raw["gates"] = {"p95_latency_slo_ms": 10}
    assert Workload.model_validate(raw).gate("p95_latency_slo_ms") == 10


def test_prices_must_exist_for_what_a_workload_uses():
    raw = _raw("cs-email-agent")
    raw["model_id"] = "some.unpriced-model"
    with pytest.raises(ValidationError, match="price"):
        Workload.model_validate(raw)
    raw = _raw("pricing-conversion")
    raw["serving"]["instance_type"] = "ml.p5.48xlarge"
    with pytest.raises(ValidationError, match="price"):
        Workload.model_validate(raw)


def test_a_model_needs_an_evaluation_block_and_unknown_fields_are_refused():
    raw = _raw("pricing-conversion")
    del raw["evaluation"]
    with pytest.raises(ValidationError, match="evaluation"):
        Workload.model_validate(raw)
    raw = _raw("pricing-conversion")
    raw["skip_gates"] = True
    with pytest.raises(ValidationError):
        Workload.model_validate(raw)
