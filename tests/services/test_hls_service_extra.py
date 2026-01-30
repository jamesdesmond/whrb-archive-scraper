from unittest import mock

import os
import tempfile

import requests
import responses
from requests import RequestException

from whrb_archive.config import load_config
from whrb_archive.services.hls_service import (
    append_segments,
    download_segments,
    fetch_playlist,
    fetch_segment,
    transcode_to_mp3,
)


@responses.activate
def test_fetch_playlist_http_not_found():
    config = load_config()
    responses.add(
        responses.GET,
        f"{config.base_archive_url}/2026_01_01_00/2026_01_01_00.m3u8",
        status=404,
    )
    session = requests.Session()
    with tempfile.TemporaryDirectory() as temp_dir:
        playlist = fetch_playlist(
            "2026_01_01_00", session, temp_dir, offline=False, config=config
        )
    assert playlist is None


def test_fetch_playlist_retry_error():
    config = load_config()
    session = requests.Session()

    def raise_error(*args, **kwargs):
        raise RequestException("boom")

    with mock.patch.object(session, "get", side_effect=raise_error):
        try:
            fetch_playlist(
                "2026_01_01_00", session, "/tmp", offline=False, config=config
            )
        except RequestException:
            assert True


def test_fetch_playlist_writes_cache():
    config = load_config()
    session = requests.Session()

    class FakeResponse:
        status_code = 200
        text = "#EXTM3U\n#EXTINF:10,\n000.ts\n"

    def fake_get(*args, **kwargs):
        return FakeResponse()

    with mock.patch.object(session, "get", side_effect=fake_get):
        playlist = fetch_playlist(
            "2026_01_01_00", session, "/tmp", offline=False, config=config
        )
    assert "000.ts" in playlist


def test_fetch_segment_writes_cache():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_path = os.path.join(temp_dir, "seg.ts")

        class FakeResponse:
            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=1024):
                yield b"data"

        session = requests.Session()
        with mock.patch.object(session, "get", return_value=FakeResponse()):
            result = fetch_segment(
                "https://example.com/seg.ts",
                cache_path,
                session,
                offline=False,
                config=config,
            )
        assert result == cache_path
        assert os.path.exists(cache_path)


def test_download_segments_failure_when_missing():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        destination = os.path.join(temp_dir, "out.ts")
        session = requests.Session()
        with mock.patch(
            "whrb_archive.services.hls_service.fetch_segment", return_value=None
        ):
            ok = download_segments(
                ["https://example.com/seg.ts"],
                destination,
                os.path.join(temp_dir, "segments"),
                session,
                offline=False,
                config=config,
            )
        assert ok is False


def test_append_segments_failure_when_missing():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        destination = os.path.join(temp_dir, "out.ts")
        session = requests.Session()
        with (
            open(destination, "wb") as handle,
            mock.patch(
                "whrb_archive.services.hls_service.fetch_segment", return_value=None
            ),
        ):
            ok = append_segments(
                ["https://example.com/seg.ts"],
                handle,
                os.path.join(temp_dir, "segments"),
                session,
                offline=False,
                config=config,
            )
        assert ok is False


def test_transcode_to_mp3_failure_returncode():
    config = load_config()
    with tempfile.TemporaryDirectory() as temp_dir:
        source = os.path.join(temp_dir, "input.ts")
        dest = os.path.join(temp_dir, "output.mp3")
        with open(source, "wb") as payload:
            payload.write(b"data")

        class FakeProcess:
            def __init__(self):
                self.stdout = ["out_time=00:00:01\n"]
                self.stderr = mock.Mock(read=lambda: "ffmpeg error")

            def wait(self):
                return 1

        with (
            mock.patch("shutil.which", return_value="ffmpeg"),
            mock.patch("subprocess.Popen", return_value=FakeProcess()),
        ):
            ok = transcode_to_mp3(source, dest, config)
        assert ok is False
