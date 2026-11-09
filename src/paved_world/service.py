"""The simulated customer-service world behind the agent workload. Truth side: the platform never imports this.

Customers write in five languages about ten things (change a booking, a deposit refund, a breakdown...). The
foundation models are simulated: how often a model with a given prompt reads the intent right, how often it
invents a fact, how long it takes and how many tokens it uses are hidden parameters here. The platform sees
only what Bedrock would return (structured output, usage, latency) and, later, what customers did.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from paved.agentkit import ActionProposal, Classification, Reply, Usage

INTENTS: dict[str, tuple[str, float, float]] = {
    # intent: (phase, share last spring (the eval set), share now (summer production))
    "change_reservation": ("before", 0.16, 0.13),
    "cancel_reservation": ("before", 0.12, 0.10),
    "pickup_documents": ("before", 0.10, 0.09),
    "station_directions": ("before", 0.06, 0.07),
    "extend_rental": ("during", 0.06, 0.07),
    "breakdown": ("during", 0.03, 0.07),
    "deposit_refund": ("after", 0.16, 0.14),
    "invoice_question": ("after", 0.14, 0.11),
    "damage_claim": ("after", 0.09, 0.13),
    "toll_fines": ("after", 0.08, 0.09),
}
LANGUAGES = ["de", "en", "fr", "es", "it"]
LANGUAGE_P = [0.34, 0.30, 0.12, 0.12, 0.12]
REFUND_LIMIT_EUR = 250.0
TOOLS_API_VERSION = "v2"

_TEMPLATES = {
    "de": "Hallo, Reservierung {res}: {topic}. Danke!",
    "en": "Hi, booking {res}: {topic}. Thanks!",
    "fr": "Bonjour, réservation {res} : {topic}. Merci !",
    "es": "Hola, reserva {res}: {topic}. ¡Gracias!",
    "it": "Ciao, prenotazione {res}: {topic}. Grazie!",
}
_TOPICS = {
    "change_reservation": "can I move the pickup to Friday",
    "cancel_reservation": "please cancel, plans changed",
    "pickup_documents": "which documents do I need at pickup",
    "station_directions": "where is the station at the airport",
    "extend_rental": "I need the car two more days",
    "breakdown": "the car broke down on the motorway",
    "deposit_refund": "my deposit of {amount} EUR is still blocked",
    "invoice_question": "what is this charge on my invoice",
    "damage_claim": "I do not agree with the damage report",
    "toll_fines": "why was I charged for a toll fine",
}

# Hidden model behaviour.
_BASE_ACCURACY = {"anthropic.claude-sonnet-4-5": 0.945, "anthropic.claude-haiku-4-5": 0.925}
_HARD_INTENT_PENALTY = {"anthropic.claude-sonnet-4-5": 0.02, "anthropic.claude-haiku-4-5": 0.05}
_HALLUCINATION = {"anthropic.claude-sonnet-4-5": 0.006, "anthropic.claude-haiku-4-5": 0.010}
_LATENCY_MS = {"anthropic.claude-sonnet-4-5": 2600.0, "anthropic.claude-haiku-4-5": 1300.0}
_PROMPT_EFFECT = {
    "v4": {},
    "v5": {"*": 0.025},
    "v5-terse": {"*": 0.010, "breakdown": -0.30, "damage_claim": -0.20},
    "v5-en-only": {"*": 0.025, "lang:fr": -0.25, "lang:es": -0.25, "lang:it": -0.25},
}
_SKIPS_POLICY = 0.7  # how often a model asked to act on a large refund just does it


@dataclass(frozen=True)
class Inquiry:
    id: str
    language: str
    phase: str
    intent: str
    amount: float
    text: str


def sample_inquiries(rng: np.random.Generator, n: int, mix: str = "now", prefix: str = "q") -> list[Inquiry]:
    names = list(INTENTS)
    p = np.array([INTENTS[k][1 if mix == "spring" else 2] for k in names])
    intents = rng.choice(names, n, p=p / p.sum())
    langs = rng.choice(LANGUAGES, n, p=LANGUAGE_P)
    amounts = np.round(np.exp(rng.normal(np.log(180), 0.6, n)), 2)
    out = []
    for i in range(n):
        res = f"{rng.integers(10**8, 10**9)}"
        topic = _TOPICS[intents[i]].format(amount=f"{amounts[i]:.2f}")
        text = _TEMPLATES[langs[i]].format(res=res, topic=topic)
        out.append(
            Inquiry(f"{prefix}{i:06d}", str(langs[i]), INTENTS[intents[i]][0], str(intents[i]), float(amounts[i]), text)
        )
    return out


def policy_suite(rng: np.random.Generator) -> list[Inquiry]:
    """Cases where the agent must not act alone: refunds above the limit and breakdowns."""
    base = sample_inquiries(rng, 2000, "spring", prefix="p")
    big = [q for q in base if q.intent == "deposit_refund" and q.amount > REFUND_LIMIT_EUR][:60]
    brk = [q for q in base if q.intent == "breakdown"][:30]
    return big + brk


def _unit(*parts: object) -> float:
    h = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64


class SimulatedBedrock:
    """Stands in for Bedrock Converse. Deterministic per (inquiry, model, prompt, call), like a cached replay."""

    def __init__(self, inquiries: dict[str, Inquiry]):
        self.inquiries = inquiries

    def _accuracy(self, q: Inquiry, meta: dict) -> float:
        model, prompt = meta["model_id"], meta["prompt_version"]
        acc = _BASE_ACCURACY[model]
        if q.intent in ("breakdown", "damage_claim"):
            acc -= _HARD_INTENT_PENALTY[model]
        eff = _PROMPT_EFFECT[prompt]
        acc += eff.get("*", 0.0) + eff.get(q.intent, 0.0) + eff.get(f"lang:{q.language}", 0.0)
        return float(np.clip(acc, 0.05, 0.995))

    def _usage(self, q: Inquiry, meta: dict, call: str, out_tokens: int) -> Usage:
        static = 2200 + 600  # system prompt and tool definitions
        dynamic = 180 + (700 if call == "reply" else 0)
        if meta.get("context") == "full_history":
            dynamic += 5200
        thinking = 1500 if meta.get("thinking") and call != "reply" else 0
        cached = meta.get("prompt_caching", False) and meta.get("context") != "full_history"
        write = cached and _unit(q.id, call, "cw") < 0.1
        cache_read = static if cached and not write else 0
        cache_write = static if write else 0
        inp = dynamic + (0 if cached else static)
        base = _LATENCY_MS[meta["model_id"]] / 3
        lat = base * np.exp(0.35 * (2 * _unit(q.id, call, "lat", meta["model_id"]) - 1) * 2)
        lat += (out_tokens + thinking) * (5.0 if "sonnet" in meta["model_id"] else 3.0)
        if meta.get("context") == "full_history":
            lat += 900
        return Usage(inp, out_tokens + thinking, cache_read, cache_write, float(lat))

    def classify(self, text: str, meta: dict) -> tuple[Classification, Usage]:
        q = self.inquiries[meta["inquiry_id"]]
        u = _unit(q.id, meta["model_id"], meta["prompt_version"], "cls")
        if u < self._accuracy(q, meta):
            intent = q.intent
        else:
            others = [k for k in INTENTS if k != q.intent]
            intent = others[int(_unit(q.id, "wrong", meta["model_id"]) * len(others))]
        conf = 0.55 + 0.4 * _unit(q.id, "conf", meta["model_id"])
        return Classification(intent, INTENTS[intent][0], conf), self._usage(q, meta, "classify", 60)

    def propose_action(self, intent: str, text: str, meta: dict) -> tuple[ActionProposal, Usage]:
        q = self.inquiries[meta["inquiry_id"]]
        usage = self._usage(q, meta, "action", 90)
        tool = {
            "change_reservation": "modify_reservation",
            "extend_rental": "modify_reservation",
            "cancel_reservation": "cancel_reservation",
            "deposit_refund": "refund_deposit",
            "invoice_question": "lookup_invoice",
            "damage_claim": "open_damage_case",
            "breakdown": "escalate",
        }.get(intent)
        if tool is None:
            return ActionProposal(None, {}), usage
        args: dict = {"reservation": q.text.split()[2].strip(":,")}
        if tool == "refund_deposit":
            args["amount_eur"] = q.amount
            if q.amount > REFUND_LIMIT_EUR and _unit(q.id, "skip", meta["model_id"]) > _SKIPS_POLICY:
                tool = "escalate"
        return ActionProposal(tool, args), usage

    def draft_reply(self, intent: str, article: dict, meta: dict) -> tuple[Reply, Usage]:
        q = self.inquiries[meta["inquiry_id"]]
        claims = dict(article)
        if claims and _unit(q.id, "halluc", meta["model_id"]) < _HALLUCINATION[meta["model_id"]]:
            k = sorted(claims)[0]
            claims[k] = f"{claims[k]}?"  # a confident, wrong detail
        text = f"[{q.language}] reply about {intent}"
        return Reply(text, claims), self._usage(q, meta, "reply", 280)


class ReservationSystem:
    """The tools the agent acts through. Production runs API v2; v2 needs `channel` on modifications."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, args: dict, tools_version: str) -> dict:
        self.calls.append((tool, args))
        if tool == "modify_reservation" and tools_version != TOOLS_API_VERSION:
            return {"ok": False, "error": "400 missing field: channel"}
        return {"ok": True, "dry_run": self.dry_run}


# What is actually true today. The agent's knowledge base is supposed to say the same.
POLICY_FACTS = {
    "deposit_refund": {"refund_days": 7},
    "toll_fines": {"admin_fee_eur": 19.5},
    "station_directions": {"airport_terminal": "T2"},
    "cancel_reservation": {"free_cancel_hours": 48},
    "pickup_documents": {"documents": "licence, ID, credit card"},
    "invoice_question": {"invoice_portal": "sixt.com/invoices"},
    "damage_claim": {"dispute_days": 14},
}


def resolution_probability(q: Inquiry, result: dict) -> tuple[float, bool]:
    """Chance the customer does not come back within three days, and whether the policy was broken."""
    violation = q.intent == "deposit_refund" and q.amount > REFUND_LIMIT_EUR and result["tool"] == "refund_deposit"
    truth = POLICY_FACTS.get(q.intent, {})
    fact_error = any(str(result["claims"].get(k)) != str(v) for k, v in truth.items() if k in result["claims"])
    if result["intent"] != q.intent:
        return 0.30, violation
    if result.get("tool_error"):
        return 0.25, violation
    if violation:
        return 0.92, True
    if result.get("escalated"):
        return 0.80, False
    if fact_error:
        return 0.45, False
    return 0.86, False
