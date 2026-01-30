"""Configuration loading for the WHRB archive downloader."""

from __future__ import annotations

import os

from .models.archive import ArchiveConfig
from .utils.retry import RetryConfig


def load_config() -> ArchiveConfig:
    """Load runtime configuration from defaults and environment variables."""
    return ArchiveConfig(
        output_dir="./recordings",
        cache_dir="./cache",
        archive_days=14,
        archive_extension="mp3",
        ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
        station_timezone="America/New_York",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        base_archive_url="https://stream.whrb.org/archive",
        schedule_url="https://api.whrb.org/schedule",
        program_schedule_url="https://www.whrb.org/programming/program-schedule/",
        request_timeout_seconds=30,
        save_playlist_file=False,
        webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
    )


RETRY_CONFIG = RetryConfig()


__all__ = [
    "load_config",
    "ArchiveConfig",
    "RETRY_CONFIG",
]
