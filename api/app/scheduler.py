"""Pure scheduling math for the daily jobs (PRD Layer 6). No IO, no global clock — ``now`` is
injected so it is fully testable. The brief fires at a local wall-clock time (e.g. 8pm IST),
computed against the configured timezone."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def next_run(
    now_utc: datetime, *, hour: int, minute: int = 0, tz: str = "Asia/Kolkata"
) -> datetime:
    """The next UTC datetime at which local ``hour:minute`` in ``tz`` occurs (today if still
    ahead, else tomorrow). ``now_utc`` must be timezone-aware."""
    zone = ZoneInfo(tz)
    now_local = now_utc.astimezone(zone)
    target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return target.astimezone(now_utc.tzinfo)


def seconds_until_next(
    now_utc: datetime, *, hour: int, minute: int = 0, tz: str = "Asia/Kolkata"
) -> float:
    return (next_run(now_utc, hour=hour, minute=minute, tz=tz) - now_utc).total_seconds()
