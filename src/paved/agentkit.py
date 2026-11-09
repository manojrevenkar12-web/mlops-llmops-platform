"""The platform's small SDK for agents: the shapes an agent's model and tool ports use.

An agent team writes its graph against these; the platform supplies the Bedrock implementation
(`paved.serving.bedrock.BedrockConverseLLM`) in production and records usage from them for cost and latency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class Classification:
    intent: str
    phase: str
    confidence: float


@dataclass
class ActionProposal:
    tool: str | None
    args: dict = field(default_factory=dict)


@dataclass
class Reply:
    text: str
    claims: dict


class LLM(Protocol):
    def classify(self, text: str, meta: dict) -> tuple[Classification, Usage]: ...
    def propose_action(self, intent: str, text: str, meta: dict) -> tuple[ActionProposal, Usage]: ...
    def draft_reply(self, intent: str, article: dict, meta: dict) -> tuple[Reply, Usage]: ...


class Tools(Protocol):
    def call(self, tool: str, args: dict, tools_version: str) -> dict: ...
