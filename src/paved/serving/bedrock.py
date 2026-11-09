"""Bedrock side of the release path for agents.

Each agent release gets an application inference profile tagged with its team and workload, so Bedrock spend
lands on the right team in Cost Explorer without anyone tagging calls by hand. The agent calls models through
`BedrockConverseLLM`, which uses the profile ARN as model id, a guardrail, prompt caching on the static prefix,
and tool use for structured output. Usage and latency come back from Converse itself.
"""

from __future__ import annotations

import json

from paved.agentkit import ActionProposal, Classification, Reply, Usage
from paved.contract import Workload


def ensure_inference_profile(client, workload: Workload, release_id: str, model_arn: str) -> str:
    resp = client.create_inference_profile(
        inferenceProfileName=f"{workload.team}-{workload.name}-{release_id}"[:64],
        description=f"{workload.name} release {release_id}",
        modelSource={"copyFrom": model_arn},
        tags=[
            {"key": "team", "value": workload.team},
            {"key": "workload", "value": workload.name},
            {"key": "release", "value": release_id},
        ],
    )
    return resp["inferenceProfileArn"]


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "toolSpec": {
            "name": name,
            "description": description,
            "inputSchema": {"json": {"type": "object", "properties": properties, "required": required}},
        }
    }


def classify_tool(intents: list[str]) -> dict:
    return _tool(
        "classify",
        "Record what the customer wants.",
        {"intent": {"type": "string", "enum": intents}, "confidence": {"type": "number"}},
        ["intent", "confidence"],
    )


ACTION = _tool(
    "propose_action",
    "Propose one reservation-system action, or none.",
    {"tool": {"type": ["string", "null"]}, "args": {"type": "object"}},
    ["tool", "args"],
)
REPLY = _tool(
    "reply",
    "Write the reply and list every fact it states.",
    {"text": {"type": "string"}, "claims": {"type": "object"}},
    ["text", "claims"],
)


class BedrockConverseLLM:
    """The agent's model port on Bedrock Converse."""

    def __init__(
        self,
        client,
        profile_arn: str,
        system_prompt: str,
        guardrail: tuple[str, str] | None,
        workload: Workload,
        phases: dict[str, str],
        caching: bool = True,
    ):
        """`phases` maps each intent the agent knows to its phase of the rental (the team's taxonomy)."""
        self.client = client
        self.phases = phases
        self.profile_arn = profile_arn
        self.system_prompt = system_prompt
        self.guardrail = guardrail
        self.workload = workload
        self.caching = caching

    def _call(self, tool: dict, content: str, meta: dict, max_tokens: int) -> tuple[dict, Usage]:
        system = [{"text": self.system_prompt}]
        if self.caching:
            system.append({"cachePoint": {"type": "default"}})
        req = {
            "modelId": self.profile_arn,
            "system": system,
            "messages": [{"role": "user", "content": [{"text": content}]}],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.0},
            "toolConfig": {"tools": [tool], "toolChoice": {"tool": {"name": tool["toolSpec"]["name"]}}},
            "requestMetadata": {
                "team": self.workload.team,
                "workload": self.workload.name,
                "inquiry": str(meta.get("inquiry_id", "")),
            },
        }
        if self.guardrail:
            req["guardrailConfig"] = {"guardrailIdentifier": self.guardrail[0], "guardrailVersion": self.guardrail[1]}
        resp = self.client.converse(**req)
        blocks = resp["output"]["message"]["content"]
        out = next(b["toolUse"]["input"] for b in blocks if "toolUse" in b)
        u = resp["usage"]
        usage = Usage(
            u["inputTokens"],
            u["outputTokens"],
            u.get("cacheReadInputTokens", 0),
            u.get("cacheWriteInputTokens", 0),
            float(resp["metrics"]["latencyMs"]),
        )
        return out, usage

    def classify(self, text: str, meta: dict) -> tuple[Classification, Usage]:
        out, u = self._call(classify_tool(sorted(self.phases)), text, meta, 100)
        intent = out["intent"]
        if intent not in self.phases:
            raise ValueError(f"model returned unknown intent {intent!r}")
        return Classification(intent, self.phases[intent], float(out["confidence"])), u

    def propose_action(self, intent: str, text: str, meta: dict) -> tuple[ActionProposal, Usage]:
        out, u = self._call(ACTION, f"Intent: {intent}\nMessage: {text}", meta, 200)
        return ActionProposal(out.get("tool"), dict(out.get("args") or {})), u

    def draft_reply(self, intent: str, article: dict, meta: dict) -> tuple[Reply, Usage]:
        out, u = self._call(REPLY, f"Intent: {intent}\nKnowledge base: {json.dumps(article)}", meta, 400)
        return Reply(out["text"], dict(out.get("claims") or {})), u
