"""Service layer for schedule, calendar, and archive operations."""

from .archive_service import fetch_and_process_whrb_archive
from .calendar_service import (
    expand_calendar_events,
    extract_calendar_ical_url,
    fetch_program_schedule_calendar,
)
from .hls_service import (
    append_segments,
    download_segments,
    fetch_playlist,
    parse_playlist,
    save_playlist_file,
    transcode_to_mp3,
)
from .schedule_service import (
    build_hourly_entries,
    build_show_blocks,
    fetch_schedule,
    find_show_for_hour,
    find_show_weekly,
    normalize_schedule,
)

__all__ = [
    "append_segments",
    "build_hourly_entries",
    "build_show_blocks",
    "download_segments",
    "expand_calendar_events",
    "extract_calendar_ical_url",
    "fetch_and_process_whrb_archive",
    "fetch_playlist",
    "fetch_program_schedule_calendar",
    "fetch_schedule",
    "find_show_for_hour",
    "find_show_weekly",
    "normalize_schedule",
    "parse_playlist",
    "save_playlist_file",
    "transcode_to_mp3",
]
