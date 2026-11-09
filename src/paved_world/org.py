"""A month of usage for a simulated data science organisation: nine teams, classical models on SageMaker and
agents on Bedrock. Volumes are invented for the simulation; prices are real list prices (config/prices.toml).
The platform's cost report reads these records the way it would read tagged AWS billing data."""

from __future__ import annotations

from paved.cost import UsageRecord

SONNET, HAIKU = "anthropic.claude-sonnet-4-5", "anthropic.claude-haiku-4-5"


def _agent(
    team: str,
    name: str,
    model: str,
    conversations: int,
    caching: bool,
    latency_class: str = "interactive",
    cheaper: str | None = None,
    calls: int = 3,
) -> UsageRecord:
    static, dynamic, out = 2800, 1240, 430
    prefix = static * calls * conversations
    return UsageRecord(
        team=team,
        workload=name,
        kind="tokens",
        model_id=model,
        requests=conversations * calls,
        input_tokens=dynamic * conversations + (0 if caching else prefix),
        output_tokens=out * conversations,
        cache_read_tokens=prefix * 0.9 if caching else 0,
        cache_write_tokens=prefix * 0.1 if caching else 0,
        static_prefix_tokens=static,
        latency_class=latency_class,
        cheaper_model_passed=cheaper,
    )


def month() -> list[UsageRecord]:
    ep = lambda team, name, itype, count, util: UsageRecord(
        team, name, "endpoint", instance_type=itype, instance_count=count, utilisation=util
    )
    return [
        ep("pricing", "pricing-conversion", "ml.m5.xlarge", 2, 0.55),
        ep("pricing", "bid-price-bandit", "ml.m5.xlarge", 4, 0.12),
        ep("revenue-mgmt", "demand-forecast", "ml.m5.large", 2, 0.40),
        ep("damage", "damage-cost", "ml.m5.large", 1, 0.30),
        ep("damage", "damage-image-triage", "ml.g5.xlarge", 3, 0.18),
        ep("customer-analytics", "churn-score", "ml.m5.large", 3, 0.08),
        ep("fleet-ops", "capacity-plan", "ml.m5.xlarge", 2, 0.35),
        ep("finance-ds", "credit-risk", "ml.m5.large", 2, 0.22),
        _agent("cs-automation", "cs-email-agent", SONNET, 600_000, caching=False, cheaper=HAIKU),
        _agent("cs-automation", "cs-chat-agent", HAIKU, 900_000, caching=True),
        _agent("cs-automation", "complaint-resolution", SONNET, 80_000, caching=True, latency_class="async"),
        _agent("branch-ops", "station-handbook-assistant", HAIKU, 120_000, caching=False),
    ]
