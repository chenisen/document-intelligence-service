"""Metrics as EMF, written to the log stream and picked up by CloudWatch.

Emission, not storage: nothing written here is readable back by the service. That is what keeps the
no-retention claim true while the analysis still leaves an operational signal behind.

One EMF blob per emission, via `single_metric`. Each of our metrics carries its own dimensions, and
batching them would force one shared dimension set on all of them.
"""

from collections.abc import Mapping

from aws_lambda_powertools.metrics import MetricUnit, single_metric

from usecases.ports import MetricsPort

NAMESPACE = "DocumentIntelligence"


class EmfMetrics(MetricsPort):
    def __init__(self, namespace: str = NAMESPACE) -> None:
        self._namespace = namespace

    def increment(self, name: str, dimensions: Mapping[str, str]) -> None:
        self.observe(name, 1.0, "Count", dimensions)

    def observe(self, name: str, value: float, unit: str, dimensions: Mapping[str, str]) -> None:
        # The port speaks plain strings; CloudWatch accepts only its own unit vocabulary, and
        # an invalid one must fail here instead of producing a metric nobody can chart.
        with single_metric(
            name=name, unit=MetricUnit(unit), value=value, namespace=self._namespace
        ) as metric:
            for key, dimension in dimensions.items():
                metric.add_dimension(name=key, value=dimension)
