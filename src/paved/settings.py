"""Settings come from config/paved.toml and config/prices.toml; nothing is repeated in code."""

from __future__ import annotations

import os
import tomllib
from functools import cache
from pathlib import Path

# The repository root (config/, workloads/, reports/). Set PAVED_ROOT when the package is installed elsewhere.
ROOT = Path(os.environ.get("PAVED_ROOT", Path(__file__).resolve().parents[2]))


@cache
def settings() -> dict:
    return tomllib.loads((ROOT / "config" / "paved.toml").read_text())


@cache
def prices() -> dict:
    return tomllib.loads((ROOT / "config" / "prices.toml").read_text())
