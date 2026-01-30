"""Calendar schedule helpers for WHRB programming."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar
from dateutil.rrule import rruleset, rrulestr
from zoneinfo import ZoneInfo

from ..errors.exceptions import ScheduleError
from ..models.archive import ArchiveConfig, ShowBlock
from ..utils.datetime_utils import ensure_datetime
from ..utils.filesystem import ensure_directory, sanitize_filename
from ..utils.retry import RetryConfig, retry

logger = logging.getLogger("whrb-archive")


def extract_calendar_ical_url(html_text: str) -> Optional[str]:
    """Extract the public iCal URL from the WHRB program schedule page."""
    soup = BeautifulSoup(html_text, "html.parser")
    iframe = soup.find("iframe")
    if not iframe or not iframe.get("src"):
        return None
    src = iframe["src"]
    if "calendar.google.com" not in src and "google.com/calendar" not in src:
        return None
    calendar_id = None
    for part in src.split("&"):
        if part.startswith("src="):
            calendar_id = part.split("=", 1)[1]
            break
    if not calendar_id:
        return None
    return (
        "https://calendar.google.com/calendar/ical/" f"{calendar_id}/public/basic.ics"
    )


def fetch_program_schedule_calendar(
    session: requests.Session,
    cache_dir: str,
    offline: bool,
    config: ArchiveConfig,
) -> Optional[str]:
    """Fetch the WHRB program schedule in iCal format."""
    cache_path = os.path.join(cache_dir, "program_schedule.ics")
    if os.path.exists(cache_path):
        logger.info("Using cached program schedule: %s", cache_path)
        with open(cache_path, "r", encoding="utf-8") as payload:
            return payload.read()
    if offline:
        logger.warning("Offline mode enabled and no cached program schedule found.")
        return None
    logger.info("Fetching program schedule page: %s", config.program_schedule_url)

    def _fetch_schedule_page() -> requests.Response:
        return session.get(
            config.program_schedule_url,
            headers={"User-Agent": config.user_agent},
            timeout=config.request_timeout_seconds,
        )

    schedule_response = retry(
        _fetch_schedule_page,
        config=RetryConfig(),
        retry_on=(requests.RequestException,),
    )
    if schedule_response.status_code != 200:
        logger.warning(
            "Program schedule page not available: %s", schedule_response.status_code
        )
        return None
    ical_url = extract_calendar_ical_url(schedule_response.text)
    if not ical_url:
        logger.warning("Unable to locate calendar URL on program schedule page.")
        return None
    logger.info("Fetching calendar feed: %s", ical_url)

    def _fetch_calendar_feed() -> requests.Response:
        return session.get(
            ical_url,
            headers={"User-Agent": config.user_agent},
            timeout=config.request_timeout_seconds,
        )

    response = retry(
        _fetch_calendar_feed,
        config=RetryConfig(),
        retry_on=(requests.RequestException,),
    )
    if response.status_code != 200:
        logger.warning("Program schedule not available: %s", response.status_code)
        return None
    ensure_directory(os.path.dirname(cache_path))
    with open(cache_path, "w", encoding="utf-8") as payload:
        payload.write(response.text)
    return response.text


def expand_calendar_events(
    ical_text: str,
    range_start: datetime,
    range_end: datetime,
    config: ArchiveConfig,
) -> list[ShowBlock]:
    """Expand iCal events into concrete show blocks within a time range."""
    timezone_local = ZoneInfo(config.station_timezone)
    calendar = Calendar.from_ical(ical_text)
    blocks: list[ShowBlock] = []
    seen: set[tuple[str, datetime, datetime]] = set()
    for component in calendar.walk("VEVENT"):
        summary = sanitize_filename(
            str(component.get("summary", "Unknown Program")).strip()
        )
        dtstart = ensure_datetime(component.get("dtstart").dt, timezone_local)
        dtend = ensure_datetime(component.get("dtend").dt, timezone_local)
        duration = dtend - dtstart
        rrule = component.get("rrule")
        if rrule:
            rrule_text = rrule.to_ical().decode()
            rset = rruleset()
            rset.rrule(rrulestr(f"RRULE:{rrule_text}", dtstart=dtstart))
            exdates = component.get("exdate")
            if exdates:
                if not isinstance(exdates, list):
                    exdates = [exdates]
                for exdate in exdates:
                    for ex in exdate.dts:
                        rset.exdate(ensure_datetime(ex.dt, timezone_local))
            for occ in rset.between(range_start, range_end, inc=True):
                start = occ
                end = occ + duration
                key = (summary or "Unknown Program", start, end)
                if key in seen:
                    continue
                seen.add(key)
                blocks.append(ShowBlock(summary or "Unknown Program", start, end))
        else:
            if dtstart < range_end and dtend > range_start:
                key = (summary or "Unknown Program", dtstart, dtend)
                if key in seen:
                    continue
                seen.add(key)
                blocks.append(ShowBlock(summary or "Unknown Program", dtstart, dtend))
    blocks.sort(key=lambda item: item.start)
    logger.info("Expanded %s schedule blocks", len(blocks))
    return blocks
