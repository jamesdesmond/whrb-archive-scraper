"""Domain models for the WHRB archive downloader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias


@dataclass(frozen=True)
class ArchiveConfig:
    """Runtime configuration for archive downloads."""

    output_dir: str
    cache_dir: str | None
    archive_days: int
    archive_extension: str
    ffmpeg_path: str
    station_timezone: str
    user_agent: str
    base_archive_url: str
    schedule_url: str
    program_schedule_url: str
    request_timeout_seconds: int
    save_playlist_file: bool
    webhook_url: str | None


@dataclass(frozen=True)
class ShowBlock:
    """Program schedule block for a single show."""

    title: str
    start: datetime
    end: datetime


ScheduleEntry: TypeAlias = ShowBlock


@dataclass(frozen=True)
class HourlyEntry:
    """Hourly archive entry for fallback downloads."""

    file_name: str
    program_name: str
    program_datetime: datetime
