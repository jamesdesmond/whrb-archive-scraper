import os
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from unittest import mock
from zoneinfo import ZoneInfo

import requests

from whrb_archive.config import load_config
from whrb_archive.models.archive import HourlyEntry, ShowBlock
from whrb_archive.services.archive_service import (
    _process_hourly_entries,
    _process_show_block,
    fetch_and_process_whrb_archive,
)


def test_fetch_and_process_whrb_archive_dry_run():
    config = load_config()
    with (
        mock.patch(
            "whrb_archive.services.archive_service.fetch_program_schedule_calendar",
            return_value=None,
        ),
        mock.patch(
            "whrb_archive.services.archive_service.build_hourly_entries",
            return_value=[],
        ),
        mock.patch(
            "whrb_archive.services.archive_service._process_hourly_entries"
        ) as mock_process,
    ):
        fetch_and_process_whrb_archive(
            days=1,
            limit=None,
            dry_run=True,
            output_dir="/tmp",
            cache_dir="/tmp",
            offline=True,
            config=config,
        )
    mock_process.assert_called_once()


def test_process_hourly_entries_skips_existing_file():
    base_config = load_config()
    config = replace(base_config, archive_extension="ts")
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="Test Show",
        program_datetime="2026_01_01_12_00_AM",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")
        os.makedirs(output_dir, exist_ok=True)
        directory = os.path.join(output_dir, entry.program_name)
        os.makedirs(directory, exist_ok=True)
        output_filename = f"{entry.program_name}_{entry.program_datetime}.ts"
        output_path = os.path.join(directory, output_filename)
        with open(output_path, "wb") as payload:
            payload.write(b"done")
        _process_hourly_entries(
            [entry],
            requests.Session(),
            cache_dir,
            output_dir,
            offline=True,
            dry_run=False,
            config=config,
        )
        assert os.path.exists(output_path)


def test_process_show_block_writes_ts():
    base_config = load_config()
    config = replace(base_config, archive_extension="ts")
    tz = ZoneInfo("America/New_York")
    block = ShowBlock(
        "Test Show",
        datetime(2026, 1, 1, 10, 0, tzinfo=tz),
        datetime(2026, 1, 1, 11, 0, tzinfo=tz),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")
        os.makedirs(output_dir, exist_ok=True)
        with (
            mock.patch(
                "whrb_archive.services.archive_service.fetch_playlist",
                return_value="#EXTM3U\n#EXTINF:10,\n000.ts\n",
            ),
            mock.patch(
                "whrb_archive.services.archive_service.parse_playlist",
                return_value=["https://example.com/000.ts"],
            ),
            mock.patch(
                "whrb_archive.services.archive_service.append_segments",
                return_value=True,
            ),
        ):
            _process_show_block(
                block,
                requests.Session(),
                cache_dir,
                output_dir,
                offline=True,
                dry_run=False,
                config=config,
                timezone_local=tz,
            )
        output_file = os.path.join(
            output_dir, "Test Show", "Test Show_2026_01_01_10_00_AM.ts"
        )
        assert os.path.exists(output_file)


def test_process_show_block_dry_run_creates_no_file():
    base_config = load_config()
    config = replace(base_config, archive_extension="ts")
    tz = ZoneInfo("America/New_York")
    block = ShowBlock(
        "Dry Run",
        datetime(2026, 1, 1, 10, 0, tzinfo=tz),
        datetime(2026, 1, 1, 11, 0, tzinfo=tz),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")
        _process_show_block(
            block,
            requests.Session(),
            cache_dir,
            output_dir,
            offline=True,
            dry_run=True,
            config=config,
            timezone_local=tz,
        )
        output_file = os.path.join(
            output_dir, "Dry Run", "Dry Run_2026_01_01_10_00_AM.ts"
        )
        assert not os.path.exists(output_file)


def test_process_hourly_entries_downloads_segments():
    base_config = load_config()
    config = replace(base_config, archive_extension="ts")
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="Test Show",
        program_datetime="2026_01_01_12_00_AM",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")

        def _write_segments(*args, **kwargs):
            destination = args[1]
            with open(destination, "wb") as payload:
                payload.write(b"data")
            return True

        with (
            mock.patch(
                "whrb_archive.services.archive_service.fetch_playlist",
                return_value="#EXTM3U\n#EXTINF:10,\n000.ts\n",
            ),
            mock.patch(
                "whrb_archive.services.archive_service.parse_playlist",
                return_value=["https://example.com/000.ts"],
            ),
            mock.patch(
                "whrb_archive.services.archive_service.download_segments",
                side_effect=_write_segments,
            ),
        ):
            _process_hourly_entries(
                [entry],
                requests.Session(),
                cache_dir,
                output_dir,
                offline=True,
                dry_run=False,
                config=config,
            )
        output_file = os.path.join(
            output_dir, "Test Show", "Test Show_2026_01_01_12_00_AM.ts"
        )
        assert os.path.exists(output_file)


def test_fetch_and_process_whrb_archive_with_show_blocks():
    config = load_config()
    tz = ZoneInfo("America/New_York")
    block = ShowBlock(
        "Show",
        datetime(2026, 1, 1, 10, 0, tzinfo=tz),
        datetime(2026, 1, 1, 11, 0, tzinfo=tz),
    )
    with (
        mock.patch(
            "whrb_archive.services.archive_service.fetch_program_schedule_calendar",
            return_value="ical",
        ),
        mock.patch(
            "whrb_archive.services.archive_service.expand_calendar_events",
            return_value=[block],
        ),
        mock.patch(
            "whrb_archive.services.archive_service.build_show_blocks",
            return_value=[block],
        ),
        mock.patch(
            "whrb_archive.services.archive_service._process_show_block"
        ) as mock_process,
    ):
        fetch_and_process_whrb_archive(
            days=1,
            limit=None,
            dry_run=True,
            output_dir="/tmp",
            cache_dir="/tmp",
            offline=True,
            config=config,
        )
    mock_process.assert_called_once()


def test_fetch_and_process_whrb_archive_fallback_schedule():
    config = load_config()
    with (
        mock.patch(
            "whrb_archive.services.archive_service.fetch_program_schedule_calendar",
            return_value=None,
        ),
        mock.patch(
            "whrb_archive.services.archive_service.fetch_schedule",
            return_value=[],
        ),
        mock.patch(
            "whrb_archive.services.archive_service.normalize_schedule",
            return_value=[],
        ),
        mock.patch(
            "whrb_archive.services.archive_service.build_hourly_entries",
            return_value=[],
        ),
        mock.patch(
            "whrb_archive.services.archive_service._process_hourly_entries"
        ) as mock_process,
    ):
        fetch_and_process_whrb_archive(
            days=1,
            limit=None,
            dry_run=True,
            output_dir="/tmp",
            cache_dir="/tmp",
            offline=True,
            config=config,
        )
    mock_process.assert_called_once()
