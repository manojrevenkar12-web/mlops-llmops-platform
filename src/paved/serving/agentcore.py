"""AgentCore side of the release path for agents.

An AgentCore Runtime endpoint points at one runtime version. A canary therefore needs two endpoints (the live one
on the champion version, a canary one on the candidate) and a split in front of them. The split is by
conversation, not by message, so a customer never talks to two agent versions in one thread.
"""

from __future__ import annotations

import hashlib


def bucket(conversation_id: str) -> float:
    """A stable number in [0, 1) per conversation."""
    return int.from_bytes(hashlib.sha256(conversation_id.encode()).digest()[:8], "big") / 2**64


class ConversationSplitter:
    def __init__(self) -> None:
        self.share = 0.0

    def endpoint_for(self, conversation_id: str) -> str:
        return "canary" if bucket(conversation_id) < self.share else "live"


class AgentCoreRouter:
    """Promote and roll back by pointing the live endpoint at a runtime version; canary by the splitter."""

    def __init__(
        self, client, runtime_id: str, champion_version: str, candidate_version: str, splitter: ConversationSplitter
    ):
        self.client = client
        self.runtime_id = runtime_id
        self.champion_version = champion_version
        self.candidate_version = candidate_version
        self.splitter = splitter

    def _point(self, endpoint: str, version: str, release_id: str, step: str) -> None:
        self.client.update_agent_runtime_endpoint(
            agentRuntimeId=self.runtime_id,
            endpointName=endpoint,
            agentRuntimeVersion=version,
            clientToken=hashlib.sha256(f"{release_id}/{step}".encode()).hexdigest(),
        )

    def shift(self, release_id: str, share: float) -> None:
        if self.splitter.share == 0.0:
            self._point("canary", self.candidate_version, release_id, "canary")
        self.splitter.share = share

    def rollback(self, release_id: str) -> None:
        self.splitter.share = 0.0

    def promote(self, release_id: str) -> None:
        self._point("live", self.candidate_version, release_id, "promote")
        self.splitter.share = 0.0
