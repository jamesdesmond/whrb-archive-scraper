"""Primary archive download workflow."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
import tempfile
from typing import Optional

import requests
from zoneinfo import ZoneInfo

from ..errors import DownloadError
from ..models.archive import ArchiveConfig, HourlyEntry, ShowBlock
from ..notifications.discord import notify_discord_on_success
from ..services.calendar_service import (
    expand_calendar_events,
    fetch_program_schedule_calendar,
)
from ..services.hls_service import (
    append_segments,
    download_segments,
    fetch_playlist,
    parse_playlist,
    save_playlist_file,
    transcode_to_mp3,
)
from ..services.schedule_service import (
    build_hourly_entries,
    build_show_blocks,
    fetch_schedule,
    normalize_schedule,
)
from ..utils.datetime_utils import iter_archive_hours
from ..utils.filesystem import ensure_directory

logger = logging.getLogger("whrb-archive")


def fetch_and_process_whrb_archive(
    days: int,
    limit: Optional[int],
    dry_run: bool,
    output_dir: str,
    cache_dir: str | None,
    offline: bool,
    config: ArchiveConfig,
) -> None:
    """Fetch and process the WHRB archive into recordings.

    Args:
        days: Number of days to scan in the archive window.
        limit: Optional cap on number of shows/hours processed.
        dry_run: When true, log work without downloading.
        output_dir: Target directory for recordings.
        cache_dir: Directory for cached schedules/playlists/segments, or None to
            disable persistent caching.
        offline: If true, rely on cached data only.
        config: Runtime configuration for the downloader.
    """

    def _run_with_cache(cache_root: str) -> None:
        session = requests.Session()
        timezone_local = ZoneInfo(config.station_timezone)
        now_utc = datetime.now(timezone.utc)
        range_end = now_utc.astimezone(timezone_local)
        range_start = range_end - timedelta(days=max(days, 1))

        logger.info("Archive range: %s to %s", range_start, range_end)
        schedule_ical = fetch_program_schedule_calendar(
            session, cache_root, offline, config
        )
        show_blocks: list[ShowBlock] = []
        if schedule_ical:
            raw_blocks = expand_calendar_events(
                schedule_ical, range_start, range_end, config
            )
            show_blocks = build_show_blocks(days, raw_blocks, config, now_utc)

        if not show_blocks:
            logger.warning("Falling back to WHRB schedule API for show names.")
            schedule_raw = fetch_schedule(
                session,
                cache_root,
                offline,
                config,
                int(now_utc.timestamp()),
            )
            schedule = normalize_schedule(schedule_raw, config)
            entries = build_hourly_entries(days, schedule, config)
            if limit:
                entries = entries[:limit]
            logger.info("Hourly entries to process: %s", len(entries))
            _process_hourly_entries(
                entries,
                session,
                cache_root,
                output_dir,
                offline,
                dry_run,
                config,
            )
            return

        if limit:
            show_blocks = show_blocks[:limit]

        logger.info("Show blocks to process: %s", len(show_blocks))
        for block in show_blocks:
            _process_show_block(
                block,
                session,
                cache_root,
                output_dir,
                offline,
                dry_run,
                config,
                timezone_local,
            )

    if cache_dir:
        _run_with_cache(cache_dir)
    else:
        if offline:
            logger.warning(
                "Offline mode requested without a cache directory; "
                "downloads will fail without cached data."
            )
        logger.info("Caching disabled; using temporary cache directory.")
        with tempfile.TemporaryDirectory() as temp_cache:
            _run_with_cache(temp_cache)


def _process_hourly_entries(
    entries: list[HourlyEntry],
    session: requests.Session,
    cache_dir: str,
    output_dir: str,
    offline: bool,
    dry_run: bool,
    config: ArchiveConfig,
) -> None:
    """Process hourly entries using the schedule API fallback.

    Args:
        entries: Hourly entries to process.
        session: Requests session for HTTP calls.
        cache_dir: Cache directory for segments and playlists.
        output_dir: Output directory for recordings.
        offline: Whether to run in offline mode.
        dry_run: When true, log work without downloading.
        config: Runtime configuration for the downloader.
    """
    for entry in entries:
        program_name = entry.program_name
        program_datetime = entry.program_datetime.strftime("%Y_%m_%d_%I_%M_%p")
        file_name = entry.file_name

        directory = os.path.join(output_dir, program_name)
        ensure_directory(directory)

        output_filename = (
            f"{program_name}_{program_datetime}.{config.archive_extension}"
        )
        output_path = os.path.join(directory, output_filename)
        temp_ts_path = output_path
        if config.archive_extension.lower() != "ts":
            temp_ts_path = os.path.join(
                directory, f"{program_name}_{program_datetime}.ts"
            )
        playlist_path = os.path.join(
            directory, f"{program_name}_{program_datetime}_playlist.m3u8"
        )

        temp_output_path = None
        if config.archive_extension.lower() == "mp3":
            temp_output_path = f"{output_path}.part"
            if os.path.exists(temp_output_path):
                logger.warning("Removing stale partial output: %s", temp_output_path)
                os.remove(temp_output_path)

        if os.path.exists(output_path):
            logger.info("Skipping existing archive: %s", output_path)
            continue

        playlist_text = fetch_playlist(file_name, session, cache_dir, offline, config)
        if not playlist_text:
            continue

        if dry_run:
            logger.info("Dry run: would download %s", output_path)
            continue

        base_url = f"{config.base_archive_url}/{file_name}/"
        segment_urls = parse_playlist(playlist_text, base_url)
        if not segment_urls:
            logger.warning("No segments found for %s", file_name)
            continue

        cache_segments_dir = os.path.join(cache_dir, file_name, "segments")
        logger.info("Downloading %s segments for %s", len(segment_urls), temp_ts_path)
        success = download_segments(
            segment_urls, temp_ts_path, cache_segments_dir, session, offline, config
        )
        if not success:
            logger.warning("Incomplete download for %s", output_path)
            continue
        if config.archive_extension.lower() == "mp3":
            logger.info("Transcoding to MP3: %s", output_path)
            target_path = temp_output_path or output_path
            if not transcode_to_mp3(temp_ts_path, target_path, config):
                if temp_ts_path != output_path and os.path.exists(temp_ts_path):
                    os.remove(temp_ts_path)
                if temp_output_path and os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
                raise DownloadError(f"ffmpeg failed for {temp_ts_path}")
            if temp_output_path:
                os.replace(temp_output_path, output_path)
            if temp_ts_path != output_path:
                os.remove(temp_ts_path)
            notify_discord_on_success(output_path, config)
        if config.save_playlist_file:
            save_playlist_file(playlist_path, playlist_text)
        elif os.path.exists(playlist_path):
            os.remove(playlist_path)


def _process_show_block(
    block: ShowBlock,
    session: requests.Session,
    cache_dir: str,
    output_dir: str,
    offline: bool,
    dry_run: bool,
    config: ArchiveConfig,
    timezone_local: ZoneInfo,
) -> None:
    """Process a single show block into a recording.

    Args:
        block: The show block to process.
        session: Requests session for HTTP calls.
        cache_dir: Cache directory for segments and playlists.
        output_dir: Output directory for recordings.
        offline: Whether to run in offline mode.
        dry_run: When true, log work without downloading.
        config: Runtime configuration for the downloader.
        timezone_local: Local timezone for log formatting.
    """
    program_name = block.title or "Unknown Program"
    start_local = block.start
    end_local = block.end
    start_label = start_local.strftime("%Y_%m_%d_%I_%M_%p")

    directory = os.path.join(output_dir, program_name)
    ensure_directory(directory)

    output_filename = f"{program_name}_{start_label}.{config.archive_extension}"
    output_path = os.path.join(directory, output_filename)
    temp_ts_path = output_path
    if config.archive_extension.lower() != "ts":
        temp_ts_path = os.path.join(directory, f"{program_name}_{start_label}.ts")
    playlist_path = os.path.join(
        directory, f"{program_name}_{start_label}_playlist.m3u8"
    )

    temp_output_path = None
    if config.archive_extension.lower() == "mp3":
        temp_output_path = f"{output_path}.part"
        if os.path.exists(temp_output_path):
            logger.warning("Removing stale partial output: %s", temp_output_path)
            os.remove(temp_output_path)

    if os.path.exists(output_path):
        logger.info("Skipping existing archive: %s", output_path)
        return

    if dry_run:
        logger.info("Dry run: would download %s", output_path)
        return

    logger.info(
        "Processing block: %s (%s to %s)",
        program_name,
        start_local,
        end_local,
    )
    hours = iter_archive_hours(start_local, end_local)
    if not hours:
        return

    has_content = False
    seen_hours: set[str] = set()
    with open(temp_ts_path, "wb") as output_file:
        for hour_utc in hours:
            file_name = hour_utc.strftime("%Y_%m_%d_%H")
            if file_name in seen_hours:
                logger.info("Skipping duplicate hour %s", file_name)
                continue
            seen_hours.add(file_name)
            hour_local_for_log = hour_utc.astimezone(timezone_local)
            hour_local_label = hour_local_for_log.strftime("%Y_%m_%d_%I_%M_%p")
            logger.info(
                "Appending hour %s (UTC) -> %s (local) to %s",
                file_name,
                hour_local_label,
                temp_ts_path,
            )
            playlist_text = fetch_playlist(
                file_name, session, cache_dir, offline, config
            )
            if not playlist_text:
                continue
            base_url = f"{config.base_archive_url}/{file_name}/"
            segment_urls = parse_playlist(playlist_text, base_url)
            if not segment_urls:
                continue
            cache_segments_dir = os.path.join(cache_dir, file_name, "segments")
            logger.info("Appending %s segments for %s", len(segment_urls), temp_ts_path)
            if not append_segments(
                segment_urls, output_file, cache_segments_dir, session, offline, config
            ):
                logger.warning("Incomplete download for %s", output_path)
                continue
            has_content = True

    if not has_content:
        if os.path.exists(temp_ts_path):
            os.remove(temp_ts_path)
        return

    if config.archive_extension.lower() == "mp3":
        logger.info("Transcoding to MP3: %s", output_path)
        target_path = temp_output_path or output_path
        if not transcode_to_mp3(temp_ts_path, target_path, config):
            if temp_ts_path != output_path and os.path.exists(temp_ts_path):
                os.remove(temp_ts_path)
            if temp_output_path and os.path.exists(temp_output_path):
                os.remove(temp_output_path)
            if os.path.exists(output_path):
                os.remove(output_path)
            raise DownloadError(f"ffmpeg failed for {temp_ts_path}")
        if temp_output_path:
            os.replace(temp_output_path, output_path)
        if temp_ts_path != output_path:
            os.remove(temp_ts_path)
        notify_discord_on_success(output_path, config)

    if os.path.exists(playlist_path):
        os.remove(playlist_path)
