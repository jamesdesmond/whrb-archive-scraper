from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from whrb_archive.utils.datetime_utils import (
    ensure_datetime,
    iter_archive_hours,
    week_minute,
)


def test_ensure_datetime_from_date():
    tz = ZoneInfo("America/New_York")
    result = ensure_datetime(date(2026, 1, 1), tz)
    assert result.tzinfo == tz
    assert result.year == 2026


def test_ensure_datetime_invalid_type():
    tz = ZoneInfo("America/New_York")
    with pytest.raises(ValueError):
        ensure_datetime("2026-01-01", tz)


def test_iter_archive_hours_count():
    tz = ZoneInfo("America/New_York")
    start_local = datetime(2026, 1, 29, 22, 0, tzinfo=tz)
    end_local = datetime(2026, 1, 30, 1, 0, tzinfo=tz)
    hours = iter_archive_hours(start_local, end_local)
    assert len(hours) == 3


def test_week_minute():
    dt = datetime(2026, 1, 5, 1, 30, tzinfo=timezone.utc)
    assert week_minute(dt) == dt.weekday() * 24 * 60 + 90
