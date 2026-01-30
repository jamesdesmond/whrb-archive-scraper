import os
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
import responses

from whrb_archive.config import load_config
from whrb_archive.models.archive import ScheduleEntry, ShowBlock
from whrb_archive.services.schedule_service import (
    build_hourly_entries,
    build_show_blocks,
    fetch_schedule,
    find_show_for_hour,
    normalize_schedule,
)


def test_find_show_for_hour_matches_schedule():
    tz = ZoneInfo("America/New_York")
    schedule = [
        ScheduleEntry(
            "Morning Show",
            datetime(2026, 1, 29, 6, 0, tzinfo=tz),
            datetime(2026, 1, 29, 10, 0, tzinfo=tz),
        ),
        ScheduleEntry(
            "Midday",
            datetime(2026, 1, 29, 10, 0, tzinfo=tz),
            datetime(2026, 1, 29, 14, 0, tzinfo=tz),
        ),
    ]
    hour_local = datetime(2026, 1, 29, 7, 0, tzinfo=tz)
    assert find_show_for_hour(hour_local, schedule) == "Morning Show"


def test_weekly_fallback_match():
    tz = ZoneInfo("America/New_York")
    schedule = [
        ScheduleEntry(
            "Weekly Show",
            datetime(2026, 1, 30, 9, 0, tzinfo=tz),
            datetime(2026, 1, 30, 11, 0, tzinfo=tz),
        )
    ]
    past_hour = datetime(2026, 1, 23, 9, 30, tzinfo=tz)
    assert find_show_for_hour(past_hour, schedule) == "Weekly Show"


def test_weekly_wraparound_match():
    tz = ZoneInfo("America/New_York")
    schedule = [
        ScheduleEntry(
            "Overnight",
            datetime(2026, 1, 30, 23, 0, tzinfo=tz),
            datetime(2026, 1, 31, 1, 0, tzinfo=tz),
        )
    ]
    past_hour = datetime(2026, 1, 23, 23, 30, tzinfo=tz)
    assert find_show_for_hour(past_hour, schedule) == "Overnight"


def test_build_hourly_entries_count():
    config = load_config()
    entries = build_hourly_entries(
        1,
        [],
        config,
        now_utc=datetime(2026, 1, 29, 12, 0, tzinfo=timezone.utc),
    )
    assert len(entries) == 24


def test_build_show_blocks_dedupes_and_skips_partial():
    config = load_config()
    tz = ZoneInfo("America/New_York")
    now_utc = datetime(2026, 1, 30, 20, 0, tzinfo=timezone.utc)
    range_end = now_utc.astimezone(tz)
    range_start = range_end - timedelta(days=1)
    blocks = [
        ShowBlock(
            "In Progress",
            range_end - timedelta(hours=1),
            range_end + timedelta(hours=1),
        ),
        ShowBlock(
            "Too Old",
            range_start - timedelta(hours=1),
            range_start + timedelta(hours=1),
        ),
        ShowBlock(
            "Full Show",
            range_end - timedelta(hours=4),
            range_end - timedelta(hours=2),
        ),
        ShowBlock(
            "Full Show",
            range_end - timedelta(hours=4),
            range_end - timedelta(hours=2),
        ),
    ]
    results = build_show_blocks(1, blocks, config, now_utc=now_utc)
    assert len(results) == 1
    assert results[0].title == "Full Show"


def test_normalize_schedule_skips_invalid():
    config = load_config()
    schedule = [
        {"startTime": "invalid", "endTime": "invalid", "title": "Bad"},
        {
            "startTime": "2026-01-01T00:00:00Z",
            "endTime": "2026-01-01T01:00:00Z",
            "title": "Good",
        },
    ]
    normalized = normalize_schedule(schedule, config)
    assert len(normalized) == 1
    assert normalized[0].title == "Good"


def test_normalize_schedule_missing_keys():
    config = load_config()
    schedule = [{"title": "Missing Keys"}]
    normalized = normalize_schedule(schedule, config)
    assert normalized == []


def test_fetch_schedule_uses_cache():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_path = os.path.join(temp_dir, "schedule.json")
        with open(cache_path, "w", encoding="utf-8") as payload:
            payload.write(
                '[{"startTime": "2026-01-01T00:00:00Z", "endTime": "2026-01-01T01:00:00Z", "title": "Cached"}]'
            )
        session = requests.Session()
        schedule = fetch_schedule(session, temp_dir, offline=True, config=config)
    assert schedule[0]["title"] == "Cached"


@responses.activate
def test_fetch_schedule_http():
    config = load_config()
    responses.add(
        responses.GET,
        config.schedule_url,
        json=[
            {
                "startTime": "2026-01-02T00:00:00Z",
                "endTime": "2026-01-02T01:00:00Z",
                "title": "Live",
            }
        ],
        status=200,
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        session = requests.Session()
        schedule = fetch_schedule(session, temp_dir, offline=False, config=config)
    assert schedule[0]["title"] == "Live"
