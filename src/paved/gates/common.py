"""What every gate returns: named checks with the value, the limit and a sentence a data scientist can act on."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Check:
    name: str
    value: float
    limit: float
    passed: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GateResult:
    stage: str
    checks: list[Check] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        bad = self.failures()
        if not bad:
            return f"{self.stage}: {len(self.checks)} checks passed"
        return f"{self.stage}: " + "; ".join(c.reason for c in bad)

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "info": self.info,
        }


def at_most(name: str, value: float, limit: float, what: str) -> Check:
    ok = value <= limit
    return Check(name, float(value), float(limit), ok, f"{what} {value:.4g} {'≤' if ok else '>'} {limit:.4g}")


def at_least(name: str, value: float, limit: float, what: str) -> Check:
    ok = value >= limit
    return Check(name, float(value), float(limit), ok, f"{what} {value:.4g} {'≥' if ok else '<'} {limit:.4g}")
