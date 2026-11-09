"""What the platform needs from the world it runs in. Production implements these with SageMaker data capture,
CloudWatch, Bedrock invocation logs and the reservation system; the evaluation implements them with a simulation.
The platform depends only on these shapes, never on how they are produced."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd


@dataclass
class ModelShadow:
    served_features: pd.DataFrame  # what the candidate endpoint received (data capture)
    logged: pd.DataFrame  # the same requests as the booking log holds them once outcomes are in
    latency_ms: np.ndarray
    errors: int


@dataclass
class ModelArm:
    value: np.ndarray  # business value per request (for pricing: revenue per offer, 0 when not booked)
    outcome: np.ndarray  # the label as it arrived (for pricing: booked)
    predicted: np.ndarray  # the arm's own prediction for the request as served
    covariate: np.ndarray  # the champion's expected value for the request, scored in shadow for both arms
    latency_ms: np.ndarray
    errors: int


@dataclass
class AgentArm:
    resolved: np.ndarray  # no recontact within three days (arrives late; the canary waits for it)
    escalated: np.ndarray
    audited: np.ndarray  # mask of conversations a person reviewed
    violation: np.ndarray  # meaningful only where audited
    cost_usd: np.ndarray
    latency_ms: np.ndarray
    tool_error: np.ndarray


@dataclass
class EvalItem:
    inquiry_id: str
    text: str
    language: str
    phase: str
    intent: str
    expected_tool: str | None
    expected_facts: dict = field(default_factory=dict)
    forbidden_tools: list[str] = field(default_factory=list)  # actions policy never lets the agent take alone


class ModelEnvironment(Protocol):
    def holdout(self) -> pd.DataFrame: ...
    def shadow(self, candidate: Any, n: int) -> ModelShadow: ...
    def canary_step(self, champion: Any, candidate: Any, share: float, n: int) -> tuple[ModelArm, ModelArm]: ...


class AgentEnvironment(Protocol):
    def eval_set(self) -> list[EvalItem]: ...
    def policy_suite(self) -> list[EvalItem]: ...
    def make_agent(self, version: Any, dry_run: bool) -> Any: ...
    def shadow(self, champion: Any, candidate: Any, n: int) -> tuple[list[dict], list[dict]]: ...
    def canary_step(self, champion: Any, candidate: Any, share: float, n: int) -> tuple[AgentArm, AgentArm]: ...
