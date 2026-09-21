from dataclasses import dataclass
from typing import Any, Literal

import boto3
from botocore.config import Config

LATENCY_TARGET_P95 = 25.0


@dataclass(frozen=True)
class Budget:
    connect: float
    read: float
    total_attempts: int

    @property
    def worst_case(self) -> float:
        return (self.connect + self.read) * self.total_attempts


Service = Literal["textract", "bedrock-runtime", "kendra"]

BUDGETS: dict[Service, Budget] = {
    "textract": Budget(connect=2.0, read=6.0, total_attempts=2),
    "bedrock-runtime": Budget(connect=2.0, read=10.0, total_attempts=2),
    "kendra": Budget(connect=1.0, read=3.0, total_attempts=2),
}


def build_client(service: Service) -> Any:
    budget = BUDGETS[service]
    return boto3.client(
        service,
        config=Config(
            connect_timeout=budget.connect,
            read_timeout=budget.read,
            retries={"total_max_attempts": budget.total_attempts, "mode": "adaptive"},
        ),
    )
