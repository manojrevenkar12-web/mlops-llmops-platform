"""The simulated production the platform is run against. Implements the platform's environment ports and keeps
the truth to itself: the platform receives only what data capture, billing and customers would show."""

from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from paved.cost import conversation_cost
from paved.ports import AgentArm, EvalItem, ModelArm, ModelShadow
from paved_workloads.cs_agent import Agent
from paved_world import mobility as mob
from paved_world import service as svc

_TOOL = {
    "change_reservation": "modify_reservation",
    "extend_rental": "modify_reservation",
    "cancel_reservation": "cancel_reservation",
    "deposit_refund": "refund_deposit",
    "invoice_question": "lookup_invoice",
    "damage_claim": "open_damage_case",
    "breakdown": "escalate",
}


def endpoint_latency(rng: np.random.Generator, complexity: int, n: int) -> np.ndarray:
    """Serving time of a tree ensemble on the endpoint's instance type grows with its size."""
    p50 = 2.0 + complexity / 2600.0
    return p50 * np.exp(rng.normal(0.0, 0.35, n))


class PricingWorld:
    def __init__(self, seed: int, log_rows: int = 300_000):
        self.seed = seed
        self.log = mob.booking_log(np.random.default_rng(seed), log_rows, -460, 0)
        self._holdout = self.log[self.log["day"] >= -14].reset_index(drop=True)

    def holdout(self) -> pd.DataFrame:
        return self._holdout

    def _rng(self, *key) -> np.random.Generator:
        return np.random.default_rng([self.seed, *(zlib.crc32(str(k).encode()) for k in key)])

    def shadow(self, candidate, n: int) -> ModelShadow:
        rng = self._rng("shadow", n)
        offers = mob.sample_offers(rng, n, 0, 3)
        served = candidate.features(offers, online=True)
        # Later, the booking log holds these requests with the outcome under the champion's price.
        logged = offers.copy()
        m = np.ones(n)
        p = mob.true_conversion(offers, m)
        booked = (rng.random(n) < p).astype(int)
        logged["upgrade_after_booking"] = (booked & (rng.random(n) < 0.6)).astype(int)
        return ModelShadow(served, logged, endpoint_latency(rng, candidate.complexity, n), int(rng.binomial(n, 0.0003)))

    def serve(self, model, champion, offers: pd.DataFrame, rng: np.random.Generator) -> ModelArm:
        m, expected = model.choose(offers, online=True)
        p_true = mob.true_conversion(offers, m)
        booked = (rng.random(len(offers)) < p_true).astype(int)
        price = mob.base_price(offers) * m
        predicted = model.predict(model.feature_frame(offers, m, online=True))
        covariate = expected if model is champion else champion.choose(offers, online=True)[1]
        return ModelArm(
            booked * price,
            booked,
            predicted,
            covariate,
            endpoint_latency(rng, model.complexity, len(offers)),
            int(rng.binomial(len(offers), 0.0003)),
        )

    def canary_step(self, champion, candidate, share: float, n: int) -> tuple[ModelArm, ModelArm]:
        rng = self._rng("canary", share, n)
        start = round(share * 20)
        offers_c = mob.sample_offers(rng, n, start, start + 1)
        offers_k = mob.sample_offers(rng, n, start, start + 1)
        return self.serve(candidate, champion, offers_c, rng), self.serve(champion, champion, offers_k, rng)

    # ---- truth, for scoring only ----
    def truth(self, model, n: int = 80_000) -> dict:
        offers = mob.sample_offers(np.random.default_rng([self.seed, 77]), n, 0, 30)
        m, _ = model.choose(offers, online=True)
        p = mob.true_conversion(offers, m)
        rev = p * mob.base_price(offers) * m
        pred = model.predict(model.feature_frame(offers, m, online=True))
        g = offers["station_type"] + "|" + offers["car_class"]
        d = pd.DataFrame({"g": g, "p": p, "q": pred}).groupby("g").agg(p=("p", "sum"), q=("q", "sum"), n=("p", "size"))
        seg = float(((d.q / d.p - 1).abs() * d.n).sum() / d.n.sum())
        p95 = float(np.percentile(endpoint_latency(np.random.default_rng(5), model.complexity, 20_000), 95))
        segments = {}
        for col in ("station_type", "car_class"):
            for v, idx in offers.groupby(col).indices.items():
                segments[f"{col}={v}"] = float(rev[idx].mean())
        return {
            "segments": segments,
            "revenue_per_offer": float(rev.mean()),
            "segment_forecast_error": seg,
            "p95_latency_ms": p95,
        }


class ServiceWorld:
    def __init__(self, seed: int, eval_size: int = 600):
        self.seed = seed
        rng = np.random.default_rng(seed)
        self._eval = svc.sample_inquiries(rng, eval_size, "spring", prefix=f"e{seed}-")
        self._suite = svc.policy_suite(np.random.default_rng([seed, 1]))
        self.registry: dict[str, svc.Inquiry] = {q.id: q for q in self._eval + self._suite}
        self.fm = svc.SimulatedBedrock(self.registry)
        noise = np.random.default_rng([seed, 2])
        names = list(svc.INTENTS)
        self._labels = {}
        for q in self._eval:  # people label the evaluation set; about 2% of labels are wrong
            self._labels[q.id] = names[noise.integers(len(names))] if noise.random() < 0.02 else q.intent
        self._cache: dict = {}

    def _item(self, q: svc.Inquiry, intent: str) -> EvalItem:
        tool = _TOOL.get(intent)
        if intent == "deposit_refund" and q.amount > svc.REFUND_LIMIT_EUR:
            tool = "escalate"
        return EvalItem(
            q.id, q.text, q.language, svc.INTENTS[intent][0], intent, tool, dict(svc.POLICY_FACTS.get(intent, {}))
        )

    def eval_set(self) -> list[EvalItem]:
        return [self._item(q, self._labels[q.id]) for q in self._eval]

    def policy_suite(self) -> list[EvalItem]:
        return [
            EvalItem(
                q.id,
                q.text,
                q.language,
                q.phase,
                q.intent,
                "escalate",
                {},
                ["refund_deposit"] if q.intent == "deposit_refund" else [],
            )
            for q in self._suite
        ]

    def make_agent(self, version, dry_run: bool) -> Agent:
        return Agent(version, self.fm, svc.ReservationSystem(dry_run))

    def _stream(self, tag: str, n: int) -> list[svc.Inquiry]:
        rng = np.random.default_rng([self.seed, zlib.crc32(tag.encode())])
        qs = svc.sample_inquiries(rng, n, "now", prefix=f"{tag}-")
        self.registry.update({q.id: q for q in qs})
        return qs

    def _run(self, version, qs: list[svc.Inquiry], dry_run: bool) -> list[dict]:
        key = (version, qs[0].id, len(qs), dry_run)
        if key not in self._cache:
            agent = self.make_agent(version, dry_run)
            self._cache[key] = [agent.handle(q.id, q.text) for q in qs]
        return self._cache[key]

    def shadow(self, champion, candidate, n: int) -> tuple[list[dict], list[dict]]:
        qs = self._stream("shadow", n)
        return self._run(champion, qs, True), self._run(candidate, qs, True)

    def _arm(self, version, qs: list[svc.Inquiry], rng: np.random.Generator) -> AgentArm:
        res = self._run(version, qs, False)
        prob, viol = zip(*(svc.resolution_probability(q, r) for q, r in zip(qs, res)))
        n = len(qs)
        return AgentArm(
            resolved=rng.random(n) < np.array(prob),
            escalated=np.array([r["escalated"] for r in res]),
            audited=rng.random(n) < 0.05,
            violation=np.array(viol),
            cost_usd=np.array([conversation_cost(r) for r in res]),
            latency_ms=np.array([r["latency_ms"] for r in res]),
            tool_error=np.array([r["tool_error"] for r in res]),
        )

    def canary_step(self, champion, candidate, share: float, n: int) -> tuple[AgentArm, AgentArm]:
        qc = self._stream(f"canary-c-{share}", n)
        qk = self._stream(f"canary-k-{share}", n)
        rng = np.random.default_rng([self.seed, int(share * 1000), n])
        return self._arm(candidate, qc, rng), self._arm(champion, qk, rng)

    # ---- truth, for scoring only ----
    def truth(self, version, n: int = 4000) -> dict:
        qs = self._stream("truth", n)
        res = self._run(version, qs, False)
        prob, viol = zip(*(svc.resolution_probability(q, r) for q, r in zip(qs, res)))
        seg: dict[str, list[float]] = {}
        for q, p in zip(qs, prob):
            seg.setdefault(f"intent={q.intent}", []).append(p)
            seg.setdefault(f"language={q.language}", []).append(p)
        return {
            "segments": {k: float(np.mean(v)) for k, v in seg.items()},
            "resolution": float(np.mean(prob)),
            "violation_rate": float(np.mean(viol)),
            "cost_per_conversation": float(np.mean([conversation_cost(r) for r in res])),
            "p95_latency_ms": float(np.percentile([r["latency_ms"] for r in res], 95)),
        }
