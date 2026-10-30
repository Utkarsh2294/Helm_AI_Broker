"""Injectable business clocks; authentication and audit timestamps stay in real UTC."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from time import monotonic
from typing import Callable, Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def wall_delay(self, duration: timedelta) -> timedelta: ...


class LiveClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def wall_delay(self, duration: timedelta) -> timedelta:
        return duration


class DemoClock:
    def __init__(
        self, start: datetime | None = None, multiplier: float = 3600, timer: Callable | None = None
    ):
        if multiplier <= 0:
            raise ValueError("Clock multiplier must be positive")
        self.start = start or wall_now()
        if self.start.tzinfo is None:
            raise ValueError("Clock reference must include a timezone")
        self.multiplier = multiplier
        self.timer = timer or monotonic
        self.reference = self.timer()

    def now(self) -> datetime:
        return self.start + timedelta(seconds=(self.timer() - self.reference) * self.multiplier)

    def wall_delay(self, duration: timedelta) -> timedelta:
        return duration / self.multiplier


def wall_now() -> datetime:
    return LiveClock().now()


def get_clock() -> Clock:
    from app.config import settings

    return _configured_clock(settings().clock_mode, settings().demo_clock_multiplier)


@lru_cache(maxsize=2)
def _configured_clock(mode, multiplier):
    return DemoClock(multiplier=multiplier) if mode == "demo" else LiveClock()
