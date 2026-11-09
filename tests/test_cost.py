import math

from paved import cost
from paved.cost import UsageRecord


def test_token_prices_follow_the_price_table():
    # 1M input + 1M output tokens on Sonnet 4.5: $3 + $15
    assert math.isclose(cost.token_cost("anthropic.claude-sonnet-4-5", 1e6, 1e6), 18.0)
    # cache reads at 10% of input, writes at 125%; batch at half price
    assert math.isclose(
        cost.token_cost("anthropic.claude-haiku-4-5", 0, 0, cache_read=1e6, cache_write=1e6), 0.1 + 1.25
    )
    assert math.isclose(cost.token_cost("anthropic.claude-haiku-4-5", 1e6, 0, batch=True), 0.5)
    assert math.isclose(cost.endpoint_month("ml.m5.xlarge", 2), 0.23 * 2 * 730)


def test_recommendations_add_up_on_one_workload():
    r = UsageRecord(
        "cs",
        "agent",
        "tokens",
        model_id="anthropic.claude-sonnet-4-5",
        requests=3_000_000,
        input_tokens=3_000_000 * 3200,
        output_tokens=1_000_000 * 430,
        static_prefix_tokens=2800,
        latency_class="async",
        cheaper_model_passed="anthropic.claude-haiku-4-5",
    )
    recs = cost.recommend(r)
    assert [x.action.split()[0] for x in recs] == ["turn", "switch", "move"]
    assert sum(x.saving_usd_month for x in recs) < cost.spend(r)


def test_endpoints_are_right_sized_only_when_underused():
    busy = UsageRecord("p", "m", "endpoint", instance_type="ml.m5.xlarge", instance_count=2, utilisation=0.6)
    idle = UsageRecord("p", "m", "endpoint", instance_type="ml.m5.xlarge", instance_count=4, utilisation=0.1)
    assert cost.recommend(busy) == []
    (rec,) = cost.recommend(idle)
    assert rec.action == "scale 4 → 1 instances" and math.isclose(rec.saving_usd_month, 0.23 * 3 * 730)
