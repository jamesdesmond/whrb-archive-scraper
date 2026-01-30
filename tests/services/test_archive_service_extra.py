import os
import tempfile
from dataclasses import replace
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import requests

from whrb_archive.config import load_config
from whrb_archive.models.archive import HourlyEntry, ShowBlock
from whrb_archive.services.archive_service import (
    _process_hourly_entries,
    _process_show_block,
)


def test_process_hourly_entries_missing_playlist():
    config = load_config()
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="Missing",
        program_datetime="2026_01_01_12_00_AM",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")
        with mock.patch(
            "whrb_archive.services.archive_service.fetch_playlist",
            return_value=None,
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
            output_dir, "Missing", "Missing_2026_01_01_12_00_AM.mp3"
        )
        assert not os.path.exists(output_file)


def test_process_hourly_entries_no_segments():
    config = load_config()
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="NoSegments",
        program_datetime="2026_01_01_12_00_AM",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")
        with (
            mock.patch(
                "whrb_archive.services.archive_service.fetch_playlist",
                return_value="#EXTM3U\n#EXTINF:10,\n000.ts\n",
            ),
            mock.patch(
                "whrb_archive.services.archive_service.parse_playlist",
                return_value=[],
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
            output_dir, "NoSegments", "NoSegments_2026_01_01_12_00_AM.mp3"
        )
        assert not os.path.exists(output_file)


def test_process_hourly_entries_transcode_failure_cleanup():
    base_config = load_config()
    config = replace(base_config, archive_extension="mp3")
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="TranscodeFail",
        program_datetime="2026_01_01_12_00_AM",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")
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
                return_value=True,
            ),
            mock.patch(
                "whrb_archive.services.archive_service.transcode_to_mp3",
                return_value=False,
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
        output_dir_show = os.path.join(output_dir, "TranscodeFail")
        assert os.path.isdir(output_dir_show)
        assert not any(name.endswith(".mp3") for name in os.listdir(output_dir_show))


def test_process_show_block_no_hours_cleans_temp_file():
    base_config = load_config()
    config = replace(base_config, archive_extension="ts")
    tz = ZoneInfo("America/New_York")
    block = ShowBlock(
        "Empty",
        datetime(2026, 1, 1, 10, 0, tzinfo=tz),
        datetime(2026, 1, 1, 10, 0, tzinfo=tz),
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
            dry_run=False,
            config=config,
            timezone_local=tz,
        )
        output_file = os.path.join(output_dir, "Empty", "Empty_2026_01_01_10_00_AM.ts")
        assert not os.path.exists(output_file)


def test_process_hourly_entries_saves_playlist_file():
    base_config = load_config()
    config = replace(base_config, archive_extension="ts", save_playlist_file=True)
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="Playlist",
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
        playlist_path = os.path.join(
            output_dir, "Playlist", "Playlist_2026_01_01_12_00_AM_playlist.m3u8"
        )
        assert os.path.exists(playlist_path)


def test_process_hourly_entries_download_failure():
    config = load_config()
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="DownloadFail",
        program_datetime="2026_01_01_12_00_AM",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")
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
                return_value=False,
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
        output_dir_show = os.path.join(output_dir, "DownloadFail")
        if os.path.exists(output_dir_show):
            assert not any(
                name.endswith(".mp3") for name in os.listdir(output_dir_show)
            )


def test_process_hourly_entries_mp3_success_cleanup():
    base_config = load_config()
    config = replace(base_config, archive_extension="mp3")
    entry = HourlyEntry(
        file_name="2026_01_01_00",
        program_name="Mp3Success",
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

        def _write_mp3(source, destination, *_args, **_kwargs):
            with open(destination, "wb") as payload:
                payload.write(b"mp3")
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
            mock.patch(
                "whrb_archive.services.archive_service.transcode_to_mp3",
                side_effect=_write_mp3,
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
        mp3_path = os.path.join(
            output_dir, "Mp3Success", "Mp3Success_2026_01_01_12_00_AM.mp3"
        )
        ts_path = os.path.join(
            output_dir, "Mp3Success", "Mp3Success_2026_01_01_12_00_AM.ts"
        )
        assert os.path.exists(mp3_path)
        assert not os.path.exists(ts_path)


def test_process_show_block_mp3_success_cleanup():
    base_config = load_config()
    config = replace(base_config, archive_extension="mp3")
    tz = ZoneInfo("America/New_York")
    block = ShowBlock(
        "BlockMp3",
        datetime(2026, 1, 1, 10, 0, tzinfo=tz),
        datetime(2026, 1, 1, 11, 0, tzinfo=tz),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = os.path.join(temp_dir, "out")
        cache_dir = os.path.join(temp_dir, "cache")

        def _append_segments(*args, **kwargs):
            handle = args[1]
            handle.write(b"data")
            return True

        def _write_mp3(source, destination, *_args, **_kwargs):
            with open(destination, "wb") as payload:
                payload.write(b"mp3")
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
                "whrb_archive.services.archive_service.append_segments",
                side_effect=_append_segments,
            ),
            mock.patch(
                "whrb_archive.services.archive_service.transcode_to_mp3",
                side_effect=_write_mp3,
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
        mp3_path = os.path.join(
            output_dir, "BlockMp3", "BlockMp3_2026_01_01_10_00_AM.mp3"
        )
        ts_path = os.path.join(
            output_dir, "BlockMp3", "BlockMp3_2026_01_01_10_00_AM.ts"
        )
        assert os.path.exists(mp3_path)
        assert not os.path.exists(ts_path)
