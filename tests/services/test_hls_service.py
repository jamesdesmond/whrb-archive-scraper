import os
import tempfile
from unittest import mock

import requests

from whrb_archive.config import load_config
from whrb_archive.services.hls_service import (
    append_segments,
    download_segments,
    fetch_playlist,
    fetch_segment,
    parse_playlist,
    transcode_to_mp3,
)


def test_parse_playlist():
    playlist = """#EXTM3U
#EXTINF:10,
000.ts
#EXTINF:10,
001.ts
"""
    urls = parse_playlist(playlist, "https://stream.whrb.org/archive/2026_01_27_00/")
    assert urls == [
        "https://stream.whrb.org/archive/2026_01_27_00/000.ts",
        "https://stream.whrb.org/archive/2026_01_27_00/001.ts",
    ]


def test_fetch_playlist_uses_cache():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        playlist_dir = os.path.join(temp_dir, "2026_01_01_00")
        os.makedirs(playlist_dir, exist_ok=True)
        cache_path = os.path.join(playlist_dir, "2026_01_01_00.m3u8")
        with open(cache_path, "w", encoding="utf-8") as payload:
            payload.write("#EXTM3U\n#EXTINF:10,\n000.ts\n")
        session = requests.Session()
        playlist = fetch_playlist(
            "2026_01_01_00", session, temp_dir, offline=True, config=config
        )
    assert "000.ts" in playlist


def test_fetch_playlist_offline_no_cache():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        session = requests.Session()
        playlist = fetch_playlist(
            "2026_01_01_00", session, temp_dir, offline=True, config=config
        )
    assert playlist is None


def test_fetch_segment_offline():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_path = os.path.join(temp_dir, "segment.ts")
        session = requests.Session()
        result = fetch_segment(
            "https://example.com/segment.ts",
            cache_path,
            session,
            offline=True,
            config=config,
        )
    assert result is None


def test_fetch_segment_uses_cache():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_path = os.path.join(temp_dir, "segment.ts")
        with open(cache_path, "wb") as payload:
            payload.write(b"cached")
        session = requests.Session()
        result = fetch_segment(
            "https://example.com/segment.ts",
            cache_path,
            session,
            offline=False,
            config=config,
        )
    assert result == cache_path


def test_download_segments_cached():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_segments_dir = os.path.join(temp_dir, "segments")
        os.makedirs(cache_segments_dir, exist_ok=True)
        for name in ["000.ts", "001.ts"]:
            with open(os.path.join(cache_segments_dir, name), "wb") as payload:
                payload.write(b"data")
        destination = os.path.join(temp_dir, "output.ts")
        session = requests.Session()
        ok = download_segments(
            [
                "https://stream.whrb.org/archive/2026_01_01_00/000.ts",
                "https://stream.whrb.org/archive/2026_01_01_00/001.ts",
            ],
            destination,
            cache_segments_dir,
            session,
            offline=True,
            config=config,
        )
    assert ok is True


def test_append_segments_cached():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_segments_dir = os.path.join(temp_dir, "segments")
        os.makedirs(cache_segments_dir, exist_ok=True)
        for name in ["000.ts", "001.ts"]:
            with open(os.path.join(cache_segments_dir, name), "wb") as payload:
                payload.write(b"data")
        destination = os.path.join(temp_dir, "output.ts")
        session = requests.Session()
        with open(destination, "wb") as output_handle:
            ok = append_segments(
                [
                    "https://stream.whrb.org/archive/2026_01_01_00/000.ts",
                    "https://stream.whrb.org/archive/2026_01_01_00/001.ts",
                ],
                output_handle,
                cache_segments_dir,
                session,
                offline=True,
                config=config,
            )
    assert ok is True


def test_transcode_to_mp3_missing_ffmpeg():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        source = os.path.join(temp_dir, "input.ts")
        dest = os.path.join(temp_dir, "output.mp3")
        with open(source, "wb") as payload:
            payload.write(b"data")
        with mock.patch("shutil.which", return_value=None):
            ok = transcode_to_mp3(source, dest, config)
    assert ok is False


def test_transcode_to_mp3_success():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        source = os.path.join(temp_dir, "input.ts")
        dest = os.path.join(temp_dir, "output.mp3")
        with open(source, "wb") as payload:
            payload.write(b"data")

        class FakeProcess:
            def __init__(self):
                self.stdout = ["out_time=00:00:01\n"]
                self.stderr = mock.Mock(read=lambda: "")

            def wait(self):
                return 0

        with (
            mock.patch("shutil.which", return_value="ffmpeg"),
            mock.patch("subprocess.Popen", return_value=FakeProcess()),
        ):
            ok = transcode_to_mp3(source, dest, config)
    assert ok is True
