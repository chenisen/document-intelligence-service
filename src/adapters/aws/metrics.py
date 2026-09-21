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
        with single_metric(
            name=name, unit=MetricUnit(unit), value=value, namespace=self._namespace
        ) as metric:
            for key, dimension in dimensions.items():
                metric.add_dimension(name=key, value=dimension)
