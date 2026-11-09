from dataclasses import replace

from paved.gates import model as gates
from paved_workloads.pricing import TrainSpec, train


def _cand(world, **kw):
    return train(world.log, replace(TrainSpec(n_estimators=80), **kw))


def test_a_retrained_model_passes_offline_and_shadow(pricing_workload, small_pricing_world, champion_model):
    cand = _cand(small_pricing_world, seed=99)
    off = gates.offline(pricing_workload, champion_model, cand, small_pricing_world.holdout())
    assert off.passed, off.summary()
    sh = gates.shadow(pricing_workload, cand, small_pricing_world.shadow(cand, 3000))
    assert sh.passed, sh.summary()


def test_training_on_the_holdout_window_is_refused(pricing_workload, small_pricing_world, champion_model):
    cand = _cand(small_pricing_world, train_to=0)
    off = gates.offline(pricing_workload, champion_model, cand, small_pricing_world.holdout())
    assert "holdout_untouched" in [c.name for c in off.failures()]


def test_a_leaky_feature_looks_great_offline_and_is_caught_by_parity(
    pricing_workload, small_pricing_world, champion_model
):
    cand = _cand(small_pricing_world, extra_features=["upgrade_after_booking"])
    off = gates.offline(pricing_workload, champion_model, cand, small_pricing_world.holdout())
    assert off.info["loss"]["rel_change"] < -0.05  # much "better" offline
    sh = gates.shadow(pricing_workload, cand, small_pricing_world.shadow(cand, 3000))
    bad = {c.name: c for c in sh.failures()}
    assert "online_offline_parity" in bad and "upgrade_after_booking" in bad["online_offline_parity"].reason


def test_unit_and_schema_changes_in_the_online_pipeline_are_caught(pricing_workload, small_pricing_world):
    for kw, feature in (
        ({"online_competitor_scale": 100.0}, "competitor_index"),
        ({"online_class_upper": True}, "car_class"),
    ):
        cand = _cand(small_pricing_world, **kw)
        sh = gates.shadow(pricing_workload, cand, small_pricing_world.shadow(cand, 2000))
        assert any(feature in c.reason for c in sh.failures()), sh.summary()


def test_stale_training_data_fails_offline(pricing_workload, small_pricing_world, champion_model):
    cand = _cand(small_pricing_world, train_from=-330, train_to=-270)
    off = gates.offline(pricing_workload, champion_model, cand, small_pricing_world.holdout())
    assert not off.passed


def test_a_heavy_model_breaks_the_latency_slo_in_shadow(pricing_workload, small_pricing_world):
    cand = _cand(small_pricing_world, n_estimators=500, num_leaves=127, learning_rate=0.01)
    sh = gates.shadow(pricing_workload, cand, small_pricing_world.shadow(cand, 2000))
    assert "p95_latency_ms" in [c.name for c in sh.failures()]
