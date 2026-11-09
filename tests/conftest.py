import numpy as np
import pytest

from paved.contract import load
from paved.settings import ROOT


@pytest.fixture(scope="session")
def pricing_workload():
    return load(ROOT / "workloads" / "pricing-conversion" / "workload.yaml")


@pytest.fixture(scope="session")
def agent_workload():
    return load(ROOT / "workloads" / "cs-email-agent" / "workload.yaml")


@pytest.fixture(scope="session")
def small_pricing_world():
    from paved_world.environment import PricingWorld

    return PricingWorld(seed=11, log_rows=150_000)


@pytest.fixture(scope="session")
def champion_model(small_pricing_world):
    from paved_workloads.pricing import TrainSpec, train

    return train(small_pricing_world.log, TrainSpec(n_estimators=80))


@pytest.fixture(scope="session")
def service_world():
    from paved_world.environment import ServiceWorld

    return ServiceWorld(seed=5, eval_size=400)


@pytest.fixture
def rng():
    return np.random.default_rng(0)
