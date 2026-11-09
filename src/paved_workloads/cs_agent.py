"""Team code for the customer-service agent: a LangGraph graph that reads a customer's message, decides what to
do, acts through the reservation tools and drafts a reply grounded in the knowledge base.

The model reads; code decides. The model classifies the message, proposes an action and drafts the reply. A plain
code node (`policy_guard`) decides whether a proposed action may run: a deposit refund above the limit and every
breakdown go to a person. A release can turn the guard off, and the platform's policy suite is what notices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from paved.agentkit import LLM, ActionProposal, Tools, Usage

REFUND_LIMIT_EUR = 250.0

# Knowledge base versions. v5 is current; v3 is the index a stale deployment would still point at.
KB: dict[str, dict[str, dict[str, Any]]] = {
    "v5": {
        "deposit_refund": {"refund_days": 7},
        "toll_fines": {"admin_fee_eur": 19.5},
        "station_directions": {"airport_terminal": "T2"},
        "cancel_reservation": {"free_cancel_hours": 48},
        "pickup_documents": {"documents": "licence, ID, credit card"},
        "invoice_question": {"invoice_portal": "sixt.com/invoices"},
        "damage_claim": {"dispute_days": 14},
    },
    "v3": {
        "deposit_refund": {"refund_days": 14},
        "toll_fines": {"admin_fee_eur": 15.0},
        "station_directions": {"airport_terminal": "T1"},
        "cancel_reservation": {"free_cancel_hours": 24},
        "pickup_documents": {"documents": "licence, ID, credit card"},
        "invoice_question": {"invoice_portal": "sixt.com/invoices"},
        "damage_claim": {"dispute_days": 14},
    },
}


@dataclass(frozen=True)
class AgentVersion:
    """Everything a release of the agent can change."""

    model_id: str = "anthropic.claude-sonnet-4-5"
    prompt_version: str = "v4"
    kb_version: str = "v5"
    policy_guard: bool = True
    prompt_caching: bool = True
    context: str = "compact"
    tools_version: str = "v2"
    thinking: bool = False

    def meta(self) -> dict:
        return asdict(self)


class State(TypedDict, total=False):
    inquiry_id: str
    text: str
    team: str
    intent: str
    phase: str
    confidence: float
    proposal: ActionProposal
    tool: str | None
    tool_error: bool
    escalated: bool
    claims: dict
    reply: str
    usage: list[Usage]


def build_graph(version: AgentVersion, llm: LLM, tools: Tools):
    meta = version.meta()

    def classify(s: State) -> State:
        c, u = llm.classify(s["text"], {**meta, "inquiry_id": s["inquiry_id"]})
        return {"intent": c.intent, "phase": c.phase, "confidence": c.confidence, "usage": [u]}

    def propose(s: State) -> State:
        p, u = llm.propose_action(s["intent"], s["text"], {**meta, "inquiry_id": s["inquiry_id"]})
        return {"proposal": p, "usage": [*s["usage"], u]}

    def policy_guard(s: State) -> State:
        p = s["proposal"]
        if p.tool == "refund_deposit" and float(p.args.get("amount_eur", 0)) > REFUND_LIMIT_EUR:
            return {"proposal": ActionProposal("escalate", p.args)}
        if s["intent"] == "breakdown":
            return {"proposal": ActionProposal("escalate", p.args)}
        return {}

    def act(s: State) -> State:
        p = s["proposal"]
        if p.tool is None:
            return {"tool": None, "tool_error": False, "escalated": False}
        if p.tool == "escalate":
            return {"tool": "escalate", "tool_error": False, "escalated": True}
        res = tools.call(p.tool, p.args, version.tools_version)
        return {"tool": p.tool, "tool_error": not res.get("ok", False), "escalated": False}

    def respond(s: State) -> State:
        article = KB[version.kb_version].get(s["intent"], {})
        r, u = llm.draft_reply(s["intent"], article, {**meta, "inquiry_id": s["inquiry_id"]})
        return {"reply": r.text, "claims": r.claims, "usage": [*s["usage"], u]}

    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("propose", propose)
    g.add_node("act", act)
    g.add_node("respond", respond)
    g.set_entry_point("classify")
    g.add_edge("classify", "propose")
    if version.policy_guard:
        g.add_node("policy_guard", policy_guard)
        g.add_edge("propose", "policy_guard")
        g.add_edge("policy_guard", "act")
    else:
        g.add_edge("propose", "act")
    g.add_edge("act", "respond")
    g.add_edge("respond", END)
    return g.compile()


class Agent:
    def __init__(self, version: AgentVersion, llm: LLM, tools: Tools):
        self.version = version
        self.graph = build_graph(version, llm, tools)

    def handle(self, inquiry_id: str, text: str) -> dict:
        s = self.graph.invoke({"inquiry_id": inquiry_id, "text": text})
        usage = s["usage"]
        return {
            "inquiry_id": inquiry_id,
            "intent": s["intent"],
            "tool": s.get("tool"),
            "tool_error": s.get("tool_error", False),
            "escalated": s.get("escalated", False),
            "claims": s.get("claims", {}),
            "input_tokens": sum(u.input_tokens for u in usage),
            "output_tokens": sum(u.output_tokens for u in usage),
            "cache_read_tokens": sum(u.cache_read_tokens for u in usage),
            "cache_write_tokens": sum(u.cache_write_tokens for u in usage),
            "latency_ms": sum(u.latency_ms for u in usage),
            "model_id": self.version.model_id,
        }
