"""Team code for a third workload, added to show onboarding: repair-cost estimates for damage reports.

A regression model (RMSE) on a handful of features. It reaches the platform with a workload.yaml and this file;
no platform code changed for it (tests/test_onboarding.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

FEATURES = ["panel", "severity", "vehicle_age_years", "car_class", "parts_index"]
_CATS = {
    "panel": ["bumper", "door", "fender", "hood", "windscreen", "mirror"],
    "car_class": ["economy", "compact", "suv", "premium", "van"],
}


def synthetic_reports(rng: np.random.Generator, n: int, day_from: int, day_to: int) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "day": rng.integers(day_from, day_to, n),
            "panel": rng.choice(_CATS["panel"], n),
            "severity": rng.integers(1, 6, n),
            "vehicle_age_years": rng.uniform(0, 4, n),
            "car_class": rng.choice(_CATS["car_class"], n),
            "parts_index": np.exp(rng.normal(0, 0.1, n)),
        }
    )
    base = df["panel"].map({"bumper": 380, "door": 620, "fender": 450, "hood": 700, "windscreen": 540, "mirror": 220})
    mult = df["car_class"].map({"economy": 0.8, "compact": 0.9, "suv": 1.1, "premium": 1.6, "van": 1.2})
    df["repair_cost"] = base * mult * df["severity"] ** 0.8 * df["parts_index"] * np.exp(rng.normal(0, 0.15, n))
    return df


@dataclass
class DamageSpec:
    train_to: int = -14
    n_estimators: int = 150


class DamageModel:
    def __init__(self, booster: lgb.Booster, spec: DamageSpec):
        self.booster, self.spec = booster, spec

    @property
    def train_to(self) -> int:
        return self.spec.train_to

    @property
    def complexity(self) -> int:
        return self.booster.num_trees() * 31

    def features(self, data: pd.DataFrame, online: bool) -> pd.DataFrame:
        f = data[FEATURES].copy()
        for c, cats in _CATS.items():
            f[c] = pd.Categorical(f[c], categories=cats)
        return f

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(frame)


def train(reports: pd.DataFrame, spec: DamageSpec) -> DamageModel:
    rows = reports[reports["day"] < spec.train_to]
    m = DamageModel(None, spec)  # type: ignore[arg-type]
    ds = lgb.Dataset(m.features(rows, False), rows["repair_cost"], categorical_feature=list(_CATS))
    params = {"objective": "regression", "verbose": -1, "num_threads": 2, "seed": 3}
    m.booster = lgb.train(params, ds, num_boost_round=spec.n_estimators)
    return m
