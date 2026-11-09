"""Team code for the pricing workload: a booking-conversion model and the price choice that uses it.

This is what a pricing data scientist owns. The platform knows nothing about it beyond the workload contract:
`train(log, spec)` returns a model with `predict(frame)`, `feature_frame(offers, online=...)`,
`choose(offers)` and `complexity`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

MULTIPLIERS = np.array([0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4])
DAILY_RATE = {"economy": 39.0, "compact": 49.0, "suv": 79.0, "premium": 129.0, "van": 99.0}
CATEGORICAL = ["station_type", "country", "car_class", "loyalty"]
BASE_FEATURES = [
    "station_type",
    "country",
    "car_class",
    "loyalty",
    "lead_days",
    "duration_days",
    "weekend",
    "competitor_index",
    "utilisation",
    "doy_sin",
    "doy_cos",
    "log_multiplier",
]
_CATEGORIES = {
    "station_type": ["airport", "city", "rail"],
    "country": ["DE", "FR", "ES", "IT", "UK", "US"],
    "car_class": ["economy", "compact", "suv", "premium", "van"],
    "loyalty": ["none", "gold", "platinum"],
}


@dataclass
class TrainSpec:
    """How a candidate was trained. Each field is something a data scientist sets in their training job."""

    train_from: int = -74
    train_to: int = -14
    n_estimators: int = 300
    num_leaves: int = 31
    learning_rate: float = 0.05
    extra_features: list[str] = field(default_factory=list)
    # A partition (column, value) the pipeline lost and backfilled from an old snapshot, `stale_by` days earlier.
    stale_partition: tuple[str, str] | None = None
    stale_by: int = 200
    # A partition (column, value) missing from training altogether.
    missing_partition: tuple[str, str] | None = None
    # Weight booked rows by multiplier**power to "emphasise high-value bookings".
    booked_weight_power: float = 0.0
    # Bugs in the online feature pipeline (the offline pipeline is correct).
    online_competitor_scale: float = 1.0
    online_class_upper: bool = False
    seed: int = 7

    @property
    def features(self) -> list[str]:
        return BASE_FEATURES + list(self.extra_features)


def _base_price(df: pd.DataFrame) -> np.ndarray:
    rate = df["car_class"].map(DAILY_RATE).to_numpy()
    dur = df["duration_days"].to_numpy()
    return rate * dur * np.where(dur >= 7, 0.9, 1.0)


class PricingModel:
    def __init__(self, booster: lgb.Booster, spec: TrainSpec):
        self.booster = booster
        self.spec = spec

    @property
    def feature_names(self) -> list[str]:
        return self.spec.features

    @property
    def train_to(self) -> int:
        return self.spec.train_to

    def features(self, data: pd.DataFrame, online: bool) -> pd.DataFrame:
        """Platform interface: features for logged rows (at the multiplier shown) or new requests (at 1.0)."""
        m = data["multiplier"].to_numpy() if "multiplier" in data else 1.0
        return self.feature_frame(data, m, online)

    @property
    def complexity(self) -> int:
        return self.booster.num_trees() * self.spec.num_leaves

    def feature_frame(self, offers: pd.DataFrame, multiplier: np.ndarray | float, online: bool) -> pd.DataFrame:
        f = pd.DataFrame(index=offers.index)
        for c in CATEGORICAL:
            values = offers[c]
            if c == "car_class" and online and self.spec.online_class_upper:
                values = values.str.upper()
            f[c] = pd.Categorical(values, categories=_CATEGORIES[c])
        lead = offers["lead_days"].to_numpy().astype(float)
        f["lead_days"] = lead
        f["duration_days"] = offers["duration_days"].to_numpy()
        comp = offers["competitor_index"].to_numpy()
        f["competitor_index"] = comp * (self.spec.online_competitor_scale if online else 1.0)
        for c in ["weekend", "utilisation"]:
            f[c] = offers[c].to_numpy()
        doy = (offers["day"].to_numpy() + 200) % 365
        f["doy_sin"] = np.sin(2 * np.pi * doy / 365)
        f["doy_cos"] = np.cos(2 * np.pi * doy / 365)
        f["log_multiplier"] = np.log(np.broadcast_to(np.asarray(multiplier, float), (len(offers),)))
        for extra in self.spec.extra_features:
            if extra == "lead_x_airport":
                f[extra] = np.log1p(lead) * (offers["station_type"].to_numpy() == "airport")
            elif extra == "upgrade_after_booking":
                # Present in the booking log, but not when the price is set: the online pipeline sends 0.
                f[extra] = 0 if online else offers[extra].to_numpy()
            else:
                raise ValueError(f"unknown feature {extra}")
        return f[self.feature_names]

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(frame)

    def choose(self, offers: pd.DataFrame, online: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """The multiplier with the highest expected revenue per offer, and that expected revenue."""
        base = _base_price(offers)
        best_m = np.full(len(offers), 1.0)
        best_rev = np.full(len(offers), -1.0)
        for m in MULTIPLIERS:
            p = self.predict(self.feature_frame(offers, m, online))
            rev = p * base * m
            better = rev > best_rev
            best_m[better], best_rev[better] = m, rev[better]
        return best_m, best_rev


def train(log: pd.DataFrame, spec: TrainSpec) -> PricingModel:
    rows = log[(log["day"] >= spec.train_from) & (log["day"] < spec.train_to)]
    if spec.stale_partition is not None:
        col, val = spec.stale_partition
        old = log[(log["day"] >= spec.train_from - spec.stale_by) & (log["day"] < spec.train_to - spec.stale_by)]
        rows = pd.concat([rows[rows[col] != val], old[old[col] == val]])
    if spec.missing_partition is not None:
        col, val = spec.missing_partition
        rows = rows[rows[col] != val]
    model = PricingModel(None, spec)  # type: ignore[arg-type]
    x = model.feature_frame(rows, rows["multiplier"].to_numpy(), online=False)
    w = np.where(rows["booked"].to_numpy() == 1, rows["multiplier"].to_numpy() ** spec.booked_weight_power, 1.0)
    params = {
        "objective": "binary",
        "num_leaves": spec.num_leaves,
        "learning_rate": spec.learning_rate,
        "min_data_in_leaf": 50,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "seed": spec.seed,
        "verbose": -1,
        "num_threads": 2,
    }
    ds = lgb.Dataset(x, rows["booked"].to_numpy(), weight=w, categorical_feature=CATEGORICAL, free_raw_data=False)
    model.booster = lgb.train(params, ds, num_boost_round=spec.n_estimators)
    return model
