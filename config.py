"""Backward-compatible config shim for legacy imports."""

from whrb_archive.config import load_config

_config = load_config()

output_dir = _config.output_dir
cache_dir = _config.cache_dir
archive_days = _config.archive_days
archive_extension = _config.archive_extension
ffmpeg_path = _config.ffmpeg_path
station_timezone = _config.station_timezone
user_agent = _config.user_agent
base_archive_url = _config.base_archive_url
schedule_url = _config.schedule_url
program_schedule_url = _config.program_schedule_url
request_timeout_seconds = _config.request_timeout_seconds
save_playlist_file = _config.save_playlist_file
webhook_url = _config.webhook_url

__all__ = [
    "output_dir",
    "cache_dir",
    "archive_days",
    "archive_extension",
    "ffmpeg_path",
    "station_timezone",
    "user_agent",
    "base_archive_url",
    "schedule_url",
    "program_schedule_url",
    "request_timeout_seconds",
    "save_playlist_file",
    "webhook_url",
]
