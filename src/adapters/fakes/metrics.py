from collections.abc import Mapping
from dataclasses import dataclass, field

from usecases.ports import MetricsPort


@dataclass(frozen=True)
class Emission:
    name: str
    value: float
    unit: str
    dimensions: Mapping[str, str]


@dataclass
class InMemoryMetrics(MetricsPort):
    emissions: list[Emission] = field(default_factory=list)

    def increment(self, name: str, dimensions: Mapping[str, str]) -> None:
        self.emissions.append(Emission(name, 1.0, "Count", dict(dimensions)))

    def observe(self, name: str, value: float, unit: str, dimensions: Mapping[str, str]) -> None:
        self.emissions.append(Emission(name, value, unit, dict(dimensions)))
