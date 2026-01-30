"""Datetime helpers for schedule calculations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def ensure_datetime(value: object, tz: ZoneInfo) -> datetime:
    """Ensure a date-like object is returned as a timezone-aware datetime."""
    if isinstance(value, datetime):
        return value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=tz)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=tz)
    raise ValueError("Unsupported datetime value")


def iter_archive_hours(start_local: datetime, end_local: datetime) -> list[datetime]:
    """Iterate hourly UTC boundaries between two localized datetimes."""
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    current = start_utc.replace(minute=0, second=0, microsecond=0)
    hours = []
    while current < end_utc:
        hours.append(current)
        current += timedelta(hours=1)
    return hours


def week_minute(dt: datetime) -> int:
    """Return a minute offset into the week for comparison logic."""
    return dt.weekday() * 24 * 60 + dt.hour * 60 + dt.minute
