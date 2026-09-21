"""How long each dependency gets, and how often it is retried.

The default boto3 timeout is a minute per attempt. In a synchronous pipeline behind a declared p95
that is not a timeout, it is a hang: the caller waits for a number nobody chose.

Each budget below is chosen from the role the dependency plays, not from a single rule:

* **Textract** is called once per page and the pages are read in sequence, so its budget is the one
  that multiplies. It gets the shortest read of the two paid calls.
* **Bedrock** is the slow one and it is essential: there is no answer without it. It gets the
  longest read, and it is the only one worth waiting for.
* **Kendra** only enriches. Its failure degrades the answer instead of failing it, so it fails fast:
  waiting twenty seconds for something the response can live without is the wrong trade.

Retries are adaptive, which is the mode that backs off when the service is already rate limiting
instead of adding load to an overloaded dependency.
"""

from dataclasses import dataclass
from typing import Any, Literal

import boto3
from botocore.config import Config

# The end-to-end target the contract declares, in seconds.
#
# The rule it produces is not "the sum fits", because it never would: pages are read in sequence,
# and a worst case where every attempt of every dependency times out is past any percentile. p95 is
# a percentile, not a ceiling on every request. The rule that must hold, and that a test enforces,
# is narrower and more useful: **no single dependency can hang past the declared p95 by itself.**
LATENCY_TARGET_P95 = 25.0


@dataclass(frozen=True)
class Budget:
    """One dependency's slice of the latency target.

    `total_attempts` is the total, first try included. botocore's own `max_attempts` counts only the
    retries and is normalised into `total_max_attempts`, which is the key this module passes so the
    number in the table means what it reads like.
    """

    connect: float
    read: float
    total_attempts: int

    @property
    def worst_case(self) -> float:
        """Every attempt timing out. No dependency may exceed the declared p95 on its own."""
        return (self.connect + self.read) * self.total_attempts


# Typed as a closed set rather than `str`: a service without a declared budget must not be reachable
# from here, and the checker is a cheaper place to find that out than production.
Service = Literal["textract", "bedrock-runtime", "kendra"]

BUDGETS: dict[Service, Budget] = {
    "textract": Budget(connect=2.0, read=6.0, total_attempts=2),
    "bedrock-runtime": Budget(connect=2.0, read=10.0, total_attempts=2),
    "kendra": Budget(connect=1.0, read=3.0, total_attempts=2),
}

# The Bedrock read is the tightest number here, and it is bound by the p95 the contract declares,
# not by what the model would like. If a model needs more than this, the honest move is to reopen
# the declared p95 with the consumer, not to quietly raise the timeout until the symptom goes away.


def build_client(service: Service) -> Any:
    """A boto3 client that fails inside a declared budget instead of hanging on a default."""
    budget = BUDGETS[service]
    return boto3.client(
        service,
        config=Config(
            connect_timeout=budget.connect,
            read_timeout=budget.read,
            retries={"total_max_attempts": budget.total_attempts, "mode": "adaptive"},
        ),
    )
