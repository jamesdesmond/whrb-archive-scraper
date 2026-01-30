"""Schedule normalization and lookup helpers."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import requests
from zoneinfo import ZoneInfo

from ..models.archive import ArchiveConfig, HourlyEntry, ScheduleEntry, ShowBlock
from ..utils.datetime_utils import week_minute
from ..utils.filesystem import sanitize_filename
from ..utils.json_cache import read_json, write_json

logger = logging.getLogger("whrb-archive")


def build_show_blocks(
    days: int,
    schedule_blocks: list[ShowBlock],
    config: ArchiveConfig,
    now_utc: Optional[datetime] = None,
) -> list[ShowBlock]:
    """Filter schedule blocks to complete shows within the archive range."""
    timezone_local = ZoneInfo(config.station_timezone)
    now_utc = now_utc or datetime.now(timezone.utc)
    range_end = now_utc.astimezone(timezone_local)
    range_start = range_end - timedelta(days=max(days, 1))
    results: list[ShowBlock] = []
    seen: set[tuple[str, datetime, datetime]] = set()
    for block in schedule_blocks:
        if block.end <= range_start or block.start >= range_end:
            continue
        if block.start < range_start or block.end > range_end:
            logger.info(
                "Skipping partial block (not fully in range): %s (%s to %s)",
                block.title,
                block.start,
                block.end,
            )
            continue
        key = (block.title, block.start, block.end)
        if key in seen:
            continue
        seen.add(key)
        results.append(block)
    results.sort(key=lambda item: item.start)
    logger.info("Show blocks in range: %s", len(results))
    return results


def fetch_schedule(
    session: requests.Session,
    cache_dir: str,
    offline: bool,
    config: ArchiveConfig,
    reference_epoch: Optional[int] = None,
) -> list[dict]:
    """Fetch schedule JSON data from WHRB's API."""
    cache_path = os.path.join(cache_dir, "schedule.json")
    if os.path.exists(cache_path):
        return read_json(cache_path)
    if offline:
        logger.warning("Offline mode enabled and no cached schedule found.")
        return []
    params = {"t": reference_epoch} if reference_epoch is not None else None
    response = session.get(
        config.schedule_url,
        params=params,
        headers={"User-Agent": config.user_agent},
        timeout=config.request_timeout_seconds,
    )
    response.raise_for_status()
    schedule = response.json()
    if not isinstance(schedule, list):
        raise ValueError("Unexpected schedule payload")
    write_json(cache_path, schedule)
    return schedule


def normalize_schedule(
    schedule: Iterable[dict],
    config: ArchiveConfig,
) -> list[ScheduleEntry]:
    """Normalize raw API schedules into typed schedule entries."""
    normalized: list[ScheduleEntry] = []
    timezone_local = ZoneInfo(config.station_timezone)
    for entry in schedule:
        try:
            start = datetime.fromisoformat(entry["startTime"])
            end = datetime.fromisoformat(entry["endTime"])
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping schedule entry due to parse error: %s", exc)
            continue
        title = sanitize_filename(str(entry.get("title", "Unknown Program")).strip())
        start_local = start.astimezone(timezone_local)
        end_local = end.astimezone(timezone_local)
        normalized.append(
            ScheduleEntry(title or "Unknown Program", start_local, end_local)
        )
    return normalized


def find_show_weekly(
    hour_local: datetime, schedule: list[ScheduleEntry]
) -> Optional[str]:
    """Match a show using weekly recurrence fallback rules."""
    if not schedule:
        return None
    target_min = week_minute(hour_local)
    week_minutes = 7 * 24 * 60
    for entry in schedule:
        start_min = week_minute(entry.start)
        end_min = week_minute(entry.end)
        if end_min <= start_min:
            end_min += week_minutes
        if start_min <= target_min < end_min:
            return entry.title
        if start_min <= target_min + week_minutes < end_min:
            return entry.title
    return None


def find_show_for_hour(hour_local: datetime, schedule: list[ScheduleEntry]) -> str:
    """Find the best matching show for a given local hour."""
    matches = [item for item in schedule if item.start <= hour_local < item.end]
    if not matches:
        weekly = find_show_weekly(hour_local, schedule)
        return weekly or "Unknown Program"
    matches.sort(key=lambda item: item.start, reverse=True)
    return matches[0].title or "Unknown Program"


def build_hourly_entries(
    days: int,
    schedule: list[ScheduleEntry],
    config: ArchiveConfig,
    now_utc: Optional[datetime] = None,
) -> list[HourlyEntry]:
    """Build hourly archive entries using the fallback schedule API."""
    total_hours = max(days, 1) * 24
    now_utc = now_utc or datetime.now(timezone.utc)
    base_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    timezone_local = ZoneInfo(config.station_timezone)

    entries: list[HourlyEntry] = []
    for offset in range(1, total_hours + 1):
        hour_utc = base_hour - timedelta(hours=offset)
        hour_local = hour_utc.astimezone(timezone_local)
        file_name = hour_utc.strftime("%Y_%m_%d_%H")
        program_datetime = hour_local
        program_name = sanitize_filename(find_show_for_hour(hour_local, schedule))
        entries.append(
            HourlyEntry(
                file_name=file_name,
                program_name=program_name or "Unknown Program",
                program_datetime=program_datetime,
            )
        )
    return entries
