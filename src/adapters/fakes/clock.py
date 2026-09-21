"""Frozen time, so provenance timestamps are assertable."""

from datetime import UTC, datetime

from usecases.ports import Clock

# The date the golden set was generated. Any fixed instant would do; a meaningful one reads better
# in a failing assertion.
DEFAULT_INSTANT = datetime(2026, 9, 18, 14, 32, 7, tzinfo=UTC)


class FixedClock(Clock):
    def __init__(self, instant: datetime = DEFAULT_INSTANT) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant
