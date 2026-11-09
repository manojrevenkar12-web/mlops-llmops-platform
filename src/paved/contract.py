"""The workload contract: one YAML file a team writes to put a model or an agent on the platform.

Models and agents share one contract and one release path. What differs by kind is checked here, once, so the
pipeline never has to guess. A team may tighten a gate; it may not loosen one below the platform's floor.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from paved.settings import prices, settings

ServingTarget = Literal["sagemaker-realtime", "sagemaker-serverless", "sagemaker-batch", "bedrock-agentcore"]


class Serving(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: ServingTarget
    instance_type: str | None = None
    instance_count: int = Field(default=1, ge=1, le=20)
    latency_class: Literal["interactive", "async"] = "interactive"

    @field_validator("instance_type")
    @classmethod
    def _known_instance(cls, v: str | None) -> str | None:
        if v is not None and v not in prices()["sagemaker"]:
            raise ValueError(f"instance type {v} has no price in config/prices.toml")
        return v


class Evaluation(BaseModel):
    """How the platform judges a model offline: the label, the metric and the slices that must not regress."""

    model_config = ConfigDict(extra="forbid")
    label: str
    metric: Literal["logloss", "rmse"] = "logloss"
    slices: list[str] = Field(default_factory=list)
    # Features whose distribution moves by design (set by a policy, not the request): excluded from skew checks.
    skew_exclude: list[str] = Field(default_factory=list)


class GateOverrides(BaseModel):
    """Stricter values a team asks for. Looser ones are refused at validation time."""

    model_config = ConfigDict(extra="forbid")
    p95_latency_slo_ms: float | None = None
    non_inferiority_rel: float | None = None
    non_inferiority_pp: float | None = None
    max_fact_error_rate: float | None = None


class Workload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,40}$")
    kind: Literal["model", "agent"]
    team: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")
    owner: str = Field(pattern=r"^[^@\s]+@[^@\s]+$")
    entrypoint: str = Field(pattern=r"^[a-zA-Z_][\w.]*:[A-Za-z_]\w*$")
    serving: Serving
    model_id: str | None = None
    budget_usd_month: float = Field(gt=0)
    evaluation: Evaluation | None = None
    gates: GateOverrides = GateOverrides()
    docs: str | None = None

    @model_validator(mode="after")
    def _kind_rules(self) -> Workload:
        if self.kind == "model":
            if self.serving.target == "bedrock-agentcore":
                raise ValueError("a model is served from SageMaker, not AgentCore")
            if self.serving.target == "sagemaker-realtime" and self.serving.instance_type is None:
                raise ValueError("a real-time endpoint needs an instance_type")
            if self.evaluation is None:
                raise ValueError("a model needs an evaluation block (label, metric, slices)")
        else:
            if self.serving.target != "bedrock-agentcore":
                raise ValueError("an agent runs on Bedrock AgentCore")
            if self.model_id not in prices()["bedrock"]:
                raise ValueError(f"model_id {self.model_id} has no price in config/prices.toml")
        self._check_floors()
        return self

    def _check_floors(self) -> None:
        kind = settings()["gates"][self.kind]
        o = self.gates
        if o.p95_latency_slo_ms is not None and o.p95_latency_slo_ms > kind["p95_latency_slo_ms"]:
            raise ValueError("p95_latency_slo_ms may only be tightened")
        if o.non_inferiority_rel is not None and o.non_inferiority_rel > kind.get("non_inferiority_rel", 0):
            raise ValueError("non_inferiority_rel may only be tightened")
        if o.non_inferiority_pp is not None and o.non_inferiority_pp > kind.get("non_inferiority_pp", 0):
            raise ValueError("non_inferiority_pp may only be tightened")
        if o.max_fact_error_rate is not None and o.max_fact_error_rate > kind.get("max_fact_error_rate", 0):
            raise ValueError("max_fact_error_rate may only be tightened")

    def gate(self, key: str) -> float:
        """The value of a gate for this workload: the team's stricter value, or the platform's."""
        value = getattr(self.gates, key, None)
        return value if value is not None else settings()["gates"][self.kind][key]

    def load_entrypoint(self):
        module, attr = self.entrypoint.split(":")
        return getattr(importlib.import_module(module), attr)


def load(path: str | Path) -> Workload:
    return Workload.model_validate(yaml.safe_load(Path(path).read_text()))
