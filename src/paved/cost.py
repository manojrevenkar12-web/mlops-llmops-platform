"""Cost: what each request, release and team spends, and where the platform sees money to save.

Prices are list prices from config/prices.toml. Spend is computed from usage the platform records (tokens per
call, instance-hours per endpoint); savings are estimates and always reported apart from spend.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace

from paved.settings import prices, settings


def token_cost(
    model_id: str,
    input_tokens: float,
    output_tokens: float,
    cache_read: float = 0,
    cache_write: float = 0,
    batch: bool = False,
) -> float:
    p = prices()["bedrock"][model_id]
    usd = (
        input_tokens * p["input_per_mtok"]
        + output_tokens * p["output_per_mtok"]
        + cache_read * p["input_per_mtok"] * p["cache_read_multiplier"]
        + cache_write * p["input_per_mtok"] * p["cache_write_multiplier"]
    ) / 1e6
    return usd * (p["batch_multiplier"] if batch else 1.0)


def conversation_cost(result: dict) -> float:
    return token_cost(
        result["model_id"],
        result["input_tokens"],
        result["output_tokens"],
        result.get("cache_read_tokens", 0),
        result.get("cache_write_tokens", 0),
    )


def endpoint_month(instance_type: str, count: int) -> float:
    return prices()["sagemaker"][instance_type] * count * settings()["cost"]["hours_per_month"]


@dataclass
class UsageRecord:
    """One month of one workload, as AWS would bill it (tags from the application inference profile or endpoint)."""

    team: str
    workload: str
    kind: str  # "endpoint" or "tokens"
    instance_type: str | None = None
    instance_count: int = 0
    utilisation: float = 0.0  # mean CPU/GPU utilisation of the endpoint
    model_id: str | None = None
    requests: int = 0
    input_tokens: float = 0
    output_tokens: float = 0
    cache_read_tokens: float = 0
    cache_write_tokens: float = 0
    static_prefix_tokens: int = 0  # system prompt and tools, identical on every call
    latency_class: str = "interactive"
    cheaper_model_passed: str | None = None  # a cheaper model that passed this workload's gates


@dataclass
class Recommendation:
    team: str
    workload: str
    action: str
    reason: str
    saving_usd_month: float

    def to_dict(self) -> dict:
        return asdict(self)


def spend(r: UsageRecord) -> float:
    if r.kind == "endpoint":
        return endpoint_month(r.instance_type, r.instance_count)  # type: ignore[arg-type]
    return token_cost(r.model_id, r.input_tokens, r.output_tokens, r.cache_read_tokens, r.cache_write_tokens)  # type: ignore[arg-type]


def recommend(r: UsageRecord) -> list[Recommendation]:
    c = settings()["cost"]
    out: list[Recommendation] = []
    if r.kind == "endpoint":
        if r.utilisation < c["low_utilisation"] and r.instance_count > 1:
            keep = max(1, round(r.instance_count * r.utilisation / 0.5 + 0.5))
            if keep < r.instance_count:
                save = endpoint_month(r.instance_type, r.instance_count) - endpoint_month(r.instance_type, keep)  # type: ignore[arg-type]
                out.append(
                    Recommendation(
                        r.team,
                        r.workload,
                        f"scale {r.instance_count} → {keep} instances",
                        f"mean utilisation {r.utilisation:.0%}",
                        save,
                    )
                )
        return out
    # Applied in order on the usage left by the previous one, so savings on one workload add up.
    cur = r
    if r.static_prefix_tokens and r.cache_read_tokens == 0 and r.requests:
        total = r.static_prefix_tokens * r.requests
        hit = c["cache_hit_rate_assumed"]
        after = replace(
            r, input_tokens=r.input_tokens - total, cache_read_tokens=total * hit, cache_write_tokens=total * (1 - hit)
        )
        if spend(after) < spend(cur):
            out.append(
                Recommendation(
                    r.team,
                    r.workload,
                    "turn on prompt caching",
                    f"{r.static_prefix_tokens} identical prefix tokens on every call",
                    spend(cur) - spend(after),
                )
            )
            cur = after
    if r.cheaper_model_passed:
        after = replace(cur, model_id=r.cheaper_model_passed)
        if spend(after) < spend(cur):
            out.append(
                Recommendation(
                    r.team,
                    r.workload,
                    f"switch to {r.cheaper_model_passed}",
                    "it passed this workload's release gates",
                    spend(cur) - spend(after),
                )
            )
            cur = after
    if r.latency_class == "async":
        out.append(
            Recommendation(
                r.team,
                r.workload,
                "move to Bedrock batch inference",
                "replies are not needed within seconds",
                spend(cur) * (1 - prices()["bedrock"][cur.model_id]["batch_multiplier"]),
            )
        )
    return out


def by_team(records: list[UsageRecord]) -> dict:
    teams: dict[str, dict] = defaultdict(lambda: {"spend_usd_month": 0.0, "workloads": 0})
    for r in records:
        teams[r.team]["spend_usd_month"] += spend(r)
        teams[r.team]["workloads"] += 1
    return dict(teams)
