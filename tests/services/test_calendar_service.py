import os
import tempfile
from datetime import datetime, timezone

import requests
import responses
import pytest
from requests import RequestException

from whrb_archive.config import load_config
from whrb_archive.services.calendar_service import (
    expand_calendar_events,
    extract_calendar_ical_url,
    fetch_program_schedule_calendar,
)


def test_extract_calendar_ical_url():
    html = '<iframe src="https://www.google.com/calendar/embed?showTitle=0&src=test%40group.calendar.google.com&ctz=America%2FNew_York"></iframe>'
    ical = extract_calendar_ical_url(html)
    assert (
        ical
        == "https://calendar.google.com/calendar/ical/test%40group.calendar.google.com/public/basic.ics"
    )


def test_extract_calendar_ical_url_invalid():
    html = '<iframe src="https://example.com"></iframe>'
    assert extract_calendar_ical_url(html) is None


def test_expand_calendar_events_rrule():
    config = load_config()
    ical_text = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260101T100000Z
DTEND:20260101T110000Z
RRULE:FREQ=DAILY;COUNT=2
SUMMARY:Test Show
END:VEVENT
END:VCALENDAR
"""
    range_start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    range_end = datetime(2026, 1, 3, 0, 0, tzinfo=timezone.utc)
    blocks = expand_calendar_events(ical_text, range_start, range_end, config)
    assert len(blocks) == 2
    assert blocks[0].title == "Test Show"


def test_fetch_program_schedule_calendar_cached():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_path = os.path.join(temp_dir, "program_schedule.ics")
        with open(cache_path, "w", encoding="utf-8") as payload:
            payload.write("cached")
        session = requests.Session()
        result = fetch_program_schedule_calendar(
            session, temp_dir, offline=True, config=config
        )
    assert result == "cached"


def test_fetch_program_schedule_calendar_offline_no_cache():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        session = requests.Session()
        result = fetch_program_schedule_calendar(
            session, temp_dir, offline=True, config=config
        )
    assert result is None


@responses.activate
def test_fetch_program_schedule_calendar_http():
    config = load_config()
    schedule_html = '<iframe src="https://www.google.com/calendar/embed?showTitle=0&src=test%40group.calendar.google.com&ctz=America%2FNew_York"></iframe>'
    responses.add(
        responses.GET,
        config.program_schedule_url,
        body=schedule_html,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://calendar.google.com/calendar/ical/test%40group.calendar.google.com/public/basic.ics",
        body="ICAL",
        status=200,
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        session = requests.Session()
        result = fetch_program_schedule_calendar(
            session, temp_dir, offline=False, config=config
        )
    assert result == "ICAL"


@responses.activate
def test_fetch_program_schedule_calendar_http_feed_error():
    config = load_config()
    schedule_html = '<iframe src="https://www.google.com/calendar/embed?showTitle=0&src=test%40group.calendar.google.com&ctz=America%2FNew_York"></iframe>'
    responses.add(
        responses.GET,
        config.program_schedule_url,
        body=schedule_html,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://calendar.google.com/calendar/ical/test%40group.calendar.google.com/public/basic.ics",
        body="Error",
        status=500,
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        session = requests.Session()
        result = fetch_program_schedule_calendar(
            session, temp_dir, offline=False, config=config
        )
    assert result is None


@responses.activate
def test_fetch_program_schedule_calendar_http_not_found():
    config = load_config()
    responses.add(
        responses.GET,
        config.program_schedule_url,
        body="Not Found",
        status=404,
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        session = requests.Session()
        result = fetch_program_schedule_calendar(
            session, temp_dir, offline=False, config=config
        )
    assert result is None


def test_fetch_program_schedule_calendar_retry_error():
    config = load_config()
    session = requests.Session()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            config.program_schedule_url,
            body=RequestException("fail"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(RequestException):
                fetch_program_schedule_calendar(
                    session, temp_dir, offline=False, config=config
                )
