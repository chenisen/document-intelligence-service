"""Real time. Not AWS, so it does not live under `aws/`."""

from datetime import UTC, datetime

from usecases.ports import Clock


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)
