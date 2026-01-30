"""HLS playlist parsing and segment download helpers."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

from ..errors.exceptions import DownloadError
from ..models.archive import ArchiveConfig
from ..utils.filesystem import ensure_directory
from ..utils.retry import RetryConfig, retry

logger = logging.getLogger("whrb-archive")


def fetch_playlist(
    file_name: str,
    session: requests.Session,
    cache_dir: str,
    offline: bool,
    config: ArchiveConfig,
) -> Optional[str]:
    """Fetch an hourly playlist, using cache when available."""
    playlist_dir = os.path.join(cache_dir, file_name)
    ensure_directory(playlist_dir)
    cache_path = os.path.join(playlist_dir, f"{file_name}.m3u8")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as payload:
            return payload.read()
    if offline:
        logger.warning("Offline mode enabled and no cached playlist for %s", file_name)
        return None
    playlist_url = f"{config.base_archive_url}/{file_name}/{file_name}.m3u8"

    def _fetch_playlist() -> requests.Response:
        return session.get(
            playlist_url,
            headers={"User-Agent": config.user_agent},
            timeout=config.request_timeout_seconds,
        )

    response = retry(
        _fetch_playlist,
        config=RetryConfig(),
        retry_on=(requests.RequestException,),
    )
    if response.status_code != 200:
        logger.warning(
            "Playlist not available: %s (status %s)", playlist_url, response.status_code
        )
        return None
    with open(cache_path, "w", encoding="utf-8") as payload:
        payload.write(response.text)
    return response.text


def parse_playlist(playlist_text: str, base_url: str) -> list[str]:
    """Parse HLS playlist text into a list of segment URLs."""
    lines = [line.strip() for line in playlist_text.splitlines() if line.strip()]
    segment_paths = [line for line in lines if not line.startswith("#")]
    return [urljoin(base_url, segment) for segment in segment_paths]


def fetch_segment(
    segment_url: str,
    cache_path: str,
    session: requests.Session,
    offline: bool,
    config: ArchiveConfig,
) -> Optional[str]:
    """Fetch an individual HLS segment into cache."""
    if os.path.exists(cache_path):
        return cache_path
    if offline:
        logger.warning("Offline mode enabled and missing segment cache: %s", cache_path)
        return None

    def _fetch_segment() -> requests.Response:
        return session.get(
            segment_url,
            headers={"User-Agent": config.user_agent},
            timeout=config.request_timeout_seconds,
            stream=True,
        )

    response = retry(
        _fetch_segment,
        config=RetryConfig(),
        retry_on=(requests.RequestException,),
    )
    response.raise_for_status()
    ensure_directory(os.path.dirname(cache_path))
    with open(cache_path, "wb") as cache_file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                cache_file.write(chunk)
    return cache_path


def download_segments(
    segment_urls: list[str],
    destination_path: str,
    cache_segments_dir: str,
    session: requests.Session,
    offline: bool,
    config: ArchiveConfig,
) -> bool:
    """Download segments and concatenate into a target file."""
    ensure_directory(cache_segments_dir)
    total_segments = len(segment_urls)
    with open(destination_path, "wb") as output_file:
        for index, segment_url in enumerate(segment_urls, start=1):
            if index == 1 or index % 25 == 0 or index == total_segments:
                logger.info("Segment progress: %s/%s", index, total_segments)
            segment_name = os.path.basename(urlparse(segment_url).path)
            cache_path = os.path.join(cache_segments_dir, segment_name)
            cached_segment = fetch_segment(
                segment_url, cache_path, session, offline, config
            )
            if not cached_segment:
                return False
            with open(cached_segment, "rb") as segment_file:
                shutil.copyfileobj(segment_file, output_file, length=1024 * 1024)
    return True


def append_segments(
    segment_urls: list[str],
    output_handle,
    cache_segments_dir: str,
    session: requests.Session,
    offline: bool,
    config: ArchiveConfig,
) -> bool:
    """Append HLS segments to an open output file handle."""
    ensure_directory(cache_segments_dir)
    total_segments = len(segment_urls)
    for index, segment_url in enumerate(segment_urls, start=1):
        if index == 1 or index % 25 == 0 or index == total_segments:
            logger.info("Segment progress: %s/%s", index, total_segments)
        segment_name = os.path.basename(urlparse(segment_url).path)
        cache_path = os.path.join(cache_segments_dir, segment_name)
        cached_segment = fetch_segment(
            segment_url, cache_path, session, offline, config
        )
        if not cached_segment:
            return False
        with open(cached_segment, "rb") as segment_file:
            shutil.copyfileobj(segment_file, output_handle, length=1024 * 1024)
    return True


def save_playlist_file(destination_path: str, playlist_text: str) -> None:
    """Persist the raw playlist text to disk."""
    with open(destination_path, "w", encoding="utf-8") as playlist_file:
        playlist_file.write(playlist_text)


def transcode_to_mp3(
    source_path: str, destination_path: str, config: ArchiveConfig
) -> bool:
    """Transcode a TS archive to MP3 using ffmpeg."""
    ffmpeg_executable = shutil.which(config.ffmpeg_path)
    if not ffmpeg_executable:
        logger.error(
            "ffmpeg not found. Install ffmpeg or set ffmpeg_path in config.py."
        )
        return False
    command = [
        ffmpeg_executable,
        "-y",
        "-i",
        source_path,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        "128k",
        "-progress",
        "pipe:1",
        "-nostats",
        destination_path,
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if not process.stdout or not process.stderr:
        return False
    for line in process.stdout:
        line = line.strip()
        if line.startswith("out_time="):
            logger.info("ffmpeg progress: %s", line.split("=", 1)[1])
    stderr_output = process.stderr.read()
    returncode = process.wait()
    if returncode != 0:
        logger.error("ffmpeg failed for %s: %s", source_path, stderr_output.strip())
        return False
    return True
