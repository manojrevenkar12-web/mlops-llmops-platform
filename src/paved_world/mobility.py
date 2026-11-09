"""The simulated car-rental market behind the pricing workload. Truth side: the platform never imports this.

Each offer is a quote shown to a customer (station, class, dates, price). Whether the customer books follows a
hidden logistic model whose price elasticity differs by segment and drifts over time, so a model trained on old
data prices wrongly today. Historical logs were collected with randomised price multipliers (exploration), which
is what makes a conversion model trainable at all.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STATION_TYPES = ["airport", "city", "rail"]
STATION_P = [0.45, 0.40, 0.15]
COUNTRIES = ["DE", "FR", "ES", "IT", "UK", "US"]
COUNTRY_P = [0.32, 0.14, 0.14, 0.12, 0.12, 0.16]
CAR_CLASSES = ["economy", "compact", "suv", "premium", "van"]
CLASS_P = [0.30, 0.28, 0.20, 0.14, 0.08]
DAILY_RATE = {"economy": 39.0, "compact": 49.0, "suv": 79.0, "premium": 129.0, "van": 99.0}
LOYALTY = ["none", "gold", "platinum"]
LOYALTY_P = [0.75, 0.18, 0.07]
MULTIPLIERS = np.array([0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4])

_STATION_EFFECT = {"airport": 0.30, "city": 0.0, "rail": -0.20}
_CLASS_EFFECT = {"economy": 0.20, "compact": 0.10, "suv": -0.10, "premium": -0.40, "van": -0.50}
_LOYALTY_EFFECT = {"none": 0.0, "gold": 0.25, "platinum": 0.45}
_ELASTICITY = {"airport": 1.5, "city": 2.4, "rail": 1.9}


def sample_offers(rng: np.random.Generator, n: int, day_from: int, day_to: int) -> pd.DataFrame:
    """Offer requests as the booking funnel sees them (no price yet). Days are relative to release day 0."""
    df = pd.DataFrame(
        {
            "day": rng.integers(day_from, day_to, n),
            "station_type": rng.choice(STATION_TYPES, n, p=STATION_P),
            "country": rng.choice(COUNTRIES, n, p=COUNTRY_P),
            "car_class": rng.choice(CAR_CLASSES, n, p=CLASS_P),
            "lead_days": np.minimum(rng.geometric(0.06, n) - 1, 120),
            "duration_days": np.minimum(rng.geometric(0.22, n), 28),
            "loyalty": rng.choice(LOYALTY, n, p=LOYALTY_P),
            "competitor_index": np.exp(rng.normal(0.0, 0.12, n)),
            "utilisation": rng.uniform(0.40, 0.98, n),
        }
    )
    df["weekend"] = ((df["day"] % 7) >= 5).astype(int)
    return df


def base_price(df: pd.DataFrame) -> np.ndarray:
    rate = df["car_class"].map(DAILY_RATE).to_numpy()
    dur = df["duration_days"].to_numpy()
    return rate * dur * np.where(dur >= 7, 0.9, 1.0)


def elasticity(df: pd.DataFrame) -> np.ndarray:
    e = df["station_type"].map(_ELASTICITY).to_numpy().astype(float)
    e = e * np.where(df["car_class"].to_numpy() == "premium", 0.7, 1.0)
    e = e * np.where(df["lead_days"].to_numpy() < 3, 0.8, 1.0)
    e = e * np.where(df["loyalty"].to_numpy() == "platinum", 0.85, 1.0)
    # Customers grew more price-sensitive over the last year: a model fitted on old data overprices today.
    day = df["day"].to_numpy()
    return e * (1.0 + 0.22 * np.tanh((day + 120) / 70.0))


def true_conversion(df: pd.DataFrame, multiplier: np.ndarray) -> np.ndarray:
    doy = (df["day"].to_numpy() + 200) % 365
    logit = (
        -0.55
        + df["station_type"].map(_STATION_EFFECT).to_numpy()
        + df["car_class"].map(_CLASS_EFFECT).to_numpy()
        + df["loyalty"].map(_LOYALTY_EFFECT).to_numpy()
        + 0.8 * np.log(df["competitor_index"].to_numpy())
        - 0.12 * np.log1p(df["lead_days"].to_numpy())
        - 0.25 * np.log(df["duration_days"].to_numpy())
        + 0.3 * np.sin(2 * np.pi * (doy - 150) / 365)
        + 0.15 * df["weekend"].to_numpy()
        - elasticity(df) * np.log(multiplier)
    )
    return 1.0 / (1.0 + np.exp(-logit))


def booking_log(rng: np.random.Generator, n: int, day_from: int, day_to: int) -> pd.DataFrame:
    """Historical quotes with randomised multipliers and the observed outcome."""
    df = sample_offers(rng, n, day_from, day_to)
    m = rng.choice(MULTIPLIERS, n)
    p = true_conversion(df, m)
    booked = (rng.random(n) < p).astype(int)
    df["multiplier"] = m
    df["price"] = base_price(df) * m
    df["booked"] = booked
    # Written by the upsell system after a booking: never available when the price is set.
    df["upgrade_after_booking"] = (booked & (rng.random(n) < 0.6)).astype(int)
    return df
