from datetime import datetime, timedelta, timezone
import pytest
from app.clock import DemoClock, LiveClock


def test_demo_clock_runs_3600_times_faster_than_live():
    elapsed = [10.0]
    start = datetime(2026, 10, 30, tzinfo=timezone.utc)
    clock = DemoClock(start, timer=lambda: elapsed[0])
    before = clock.now()
    elapsed[0] += 1
    assert clock.now() - before == timedelta(hours=1)
    assert clock.wall_delay(timedelta(hours=6)) == timedelta(seconds=6)


def test_live_clock_keeps_real_durations_and_utc():
    clock = LiveClock()
    assert clock.now().tzinfo is timezone.utc
    assert clock.wall_delay(timedelta(hours=6)) == timedelta(hours=6)


def test_invalid_demo_clock_is_rejected():
    with pytest.raises(ValueError):
        DemoClock(multiplier=0)
    with pytest.raises(ValueError):
        DemoClock(datetime(2026, 10, 30))
