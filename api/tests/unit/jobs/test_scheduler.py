"""Pure scheduling math — deterministic with an injected clock."""

from __future__ import annotations

from datetime import UTC, datetime

from app.scheduler import next_run, seconds_until_next


def test_seconds_until_8pm_ist_later_today() -> None:
    # 10:00 UTC == 15:30 IST; next 20:00 IST is 4h30m away.
    now = datetime(2026, 6, 24, 10, 0, tzinfo=UTC)
    assert seconds_until_next(now, hour=20, minute=0, tz="Asia/Kolkata") == 16200


def test_rolls_to_tomorrow_when_time_passed() -> None:
    # 16:00 UTC == 21:30 IST, past 20:00 -> next is tomorrow 20:00 IST (22h30m away).
    now = datetime(2026, 6, 24, 16, 0, tzinfo=UTC)
    assert seconds_until_next(now, hour=20, minute=0, tz="Asia/Kolkata") == 81000


def test_next_run_is_in_the_future() -> None:
    now = datetime(2026, 6, 24, 16, 0, tzinfo=UTC)
    assert next_run(now, hour=20, tz="Asia/Kolkata") > now
