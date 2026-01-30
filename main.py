import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar
from dateutil.rrule import rruleset, rrulestr
from zoneinfo import ZoneInfo

import config

logger = logging.getLogger("whrb-archive")


class DiscordWebhookHandler(logging.Handler):
    def __init__(self, webhook_url: str, timeout: int = 10) -> None:
        super().__init__()
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.session = requests.Session()

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        if not message:
            return
        try:
            self.session.post(
                self.webhook_url,
                json={"content": message},
                timeout=self.timeout,
            )
        except requests.RequestException:
            # Avoid logging here to prevent recursive handler calls.
            return


def configure_logging() -> None:
    logger_root = logging.getLogger()
    logger_root.setLevel(logging.INFO)

    stream_format = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s",
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(stream_format)
    logger_root.addHandler(stream_handler)

    logger_root.info("Script Startup")


def notify_discord_on_success(path: str) -> None:
    if not config.webhook_url:
        return
    handler = DiscordWebhookHandler(
        config.webhook_url,
        timeout=config.request_timeout_seconds,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="whrb-archive",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=f"MP3 created: {path}",
        args=(),
        exc_info=None,
    )
    handler.emit(record)


def sanitize_filename(filename: str) -> str:
    invalid_chars = r"[\\/:*?\"<>|\x00-\x1F\x7F]"
    return re.sub(invalid_chars, "", filename).strip()


def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_json(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as payload:
        return json.load(payload)


def write_json(path: str, data: List[dict]) -> None:
    ensure_directory(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as payload:
        json.dump(data, payload)


def ensure_datetime(value: object, tz: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=tz)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=tz)
    raise ValueError("Unsupported datetime value")


def extract_calendar_ical_url(html_text: str) -> Optional[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    iframe = soup.find("iframe")
    if not iframe or not iframe.get("src"):
        return None
    src = iframe["src"]
    if "calendar.google.com" not in src and "google.com/calendar" not in src:
        return None
    calendar_id = None
    for part in src.split("&"):
        if part.startswith("src="):
            calendar_id = part.split("=", 1)[1]
            break
    if not calendar_id:
        return None
    return (
        "https://calendar.google.com/calendar/ical/" f"{calendar_id}/public/basic.ics"
    )


def fetch_program_schedule_calendar(
    session: requests.Session,
    cache_dir: str,
    offline: bool,
) -> Optional[str]:
    cache_path = os.path.join(cache_dir, "program_schedule.ics")
    if os.path.exists(cache_path):
        logger.info("Using cached program schedule: %s", cache_path)
        return open(cache_path, "r", encoding="utf-8").read()
    if offline:
        logger.warning("Offline mode enabled and no cached program schedule found.")
        return None
    logger.info("Fetching program schedule page: %s", config.program_schedule_url)
    schedule_response = session.get(
        config.program_schedule_url,
        headers={"User-Agent": config.user_agent},
        timeout=config.request_timeout_seconds,
    )
    if schedule_response.status_code != 200:
        logger.warning(
            "Program schedule page not available: %s", schedule_response.status_code
        )
        return None
    ical_url = extract_calendar_ical_url(schedule_response.text)
    if not ical_url:
        logger.warning("Unable to locate calendar URL on program schedule page.")
        return None
    logger.info("Fetching calendar feed: %s", ical_url)
    response = session.get(
        ical_url,
        headers={"User-Agent": config.user_agent},
        timeout=config.request_timeout_seconds,
    )
    if response.status_code != 200:
        logger.warning("Program schedule not available: %s", response.status_code)
        return None
    ensure_directory(os.path.dirname(cache_path))
    with open(cache_path, "w", encoding="utf-8") as payload:
        payload.write(response.text)
    return response.text


def expand_calendar_events(
    ical_text: str,
    range_start: datetime,
    range_end: datetime,
) -> List[dict]:
    timezone_local = ZoneInfo(config.station_timezone)
    calendar = Calendar.from_ical(ical_text)
    blocks: List[dict] = []
    seen: set[tuple[str, datetime, datetime]] = set()
    for component in calendar.walk("VEVENT"):
        summary = sanitize_filename(
            str(component.get("summary", "Unknown Program")).strip()
        )
        dtstart = ensure_datetime(component.get("dtstart").dt, timezone_local)
        dtend = ensure_datetime(component.get("dtend").dt, timezone_local)
        duration = dtend - dtstart
        rrule = component.get("rrule")
        if rrule:
            rrule_text = rrule.to_ical().decode()
            rset = rruleset()
            rset.rrule(rrulestr(f"RRULE:{rrule_text}", dtstart=dtstart))
            exdates = component.get("exdate")
            if exdates:
                if not isinstance(exdates, list):
                    exdates = [exdates]
                for exdate in exdates:
                    for ex in exdate.dts:
                        rset.exdate(ensure_datetime(ex.dt, timezone_local))
            for occ in rset.between(range_start, range_end, inc=True):
                start = occ
                end = occ + duration
                key = (summary or "Unknown Program", start, end)
                if key in seen:
                    continue
                seen.add(key)
                blocks.append(
                    {
                        "title": summary or "Unknown Program",
                        "start": start,
                        "end": end,
                    }
                )
        else:
            if dtstart < range_end and dtend > range_start:
                key = (summary or "Unknown Program", dtstart, dtend)
                if key in seen:
                    continue
                seen.add(key)
                blocks.append(
                    {
                        "title": summary or "Unknown Program",
                        "start": dtstart,
                        "end": dtend,
                    }
                )
    blocks.sort(key=lambda item: item["start"])
    logger.info("Expanded %s schedule blocks", len(blocks))
    return blocks


def build_show_blocks(
    days: int,
    schedule_blocks: List[dict],
    now_utc: Optional[datetime] = None,
) -> List[dict]:
    timezone_local = ZoneInfo(config.station_timezone)
    now_utc = now_utc or datetime.now(timezone.utc)
    range_end = now_utc.astimezone(timezone_local)
    range_start = range_end - timedelta(days=max(days, 1))
    results = []
    seen: set[tuple[str, datetime, datetime]] = set()
    for block in schedule_blocks:
        if block["end"] <= range_start or block["start"] >= range_end:
            continue
        if block["start"] < range_start or block["end"] > range_end:
            logger.info(
                "Skipping partial block (not fully in range): %s (%s to %s)",
                block["title"],
                block["start"],
                block["end"],
            )
            continue
        start_local = block["start"]
        end_local = block["end"]
        key = (block["title"], start_local, end_local)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "title": block["title"],
                "start": start_local,
                "end": end_local,
            }
        )
    results.sort(key=lambda item: item["start"])
    logger.info("Show blocks in range: %s", len(results))
    return results


def fetch_schedule(
    session: requests.Session,
    cache_dir: str,
    offline: bool,
    reference_epoch: Optional[int] = None,
) -> List[dict]:
    cache_path = os.path.join(cache_dir, "schedule.json")
    if os.path.exists(cache_path):
        return read_json(cache_path)
    if offline:
        logger.warning("Offline mode enabled and no cached schedule found.")
        return []
    params = {"t": reference_epoch} if reference_epoch is not None else None
    response = session.get(
        config.schedule_url,
        params=params,
        headers={"User-Agent": config.user_agent},
        timeout=config.request_timeout_seconds,
    )
    response.raise_for_status()
    schedule = response.json()
    if not isinstance(schedule, list):
        raise ValueError("Unexpected schedule payload")
    write_json(cache_path, schedule)
    return schedule


def normalize_schedule(schedule: Iterable[dict]) -> List[dict]:
    normalized = []
    timezone_local = ZoneInfo(config.station_timezone)
    for entry in schedule:
        try:
            start = datetime.fromisoformat(entry["startTime"])
            end = datetime.fromisoformat(entry["endTime"])
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping schedule entry due to parse error: %s", exc)
            continue
        title = sanitize_filename(str(entry.get("title", "Unknown Program")).strip())
        start_local = start.astimezone(timezone_local)
        end_local = end.astimezone(timezone_local)
        normalized.append(
            {
                "title": title or "Unknown Program",
                "start": start_local,
                "end": end_local,
            }
        )
    return normalized


def week_minute(dt: datetime) -> int:
    return dt.weekday() * 24 * 60 + dt.hour * 60 + dt.minute


def find_show_weekly(hour_local: datetime, schedule: List[dict]) -> Optional[str]:
    if not schedule:
        return None
    target_min = week_minute(hour_local)
    week_minutes = 7 * 24 * 60
    for entry in schedule:
        start_min = week_minute(entry["start"])
        end_min = week_minute(entry["end"])
        if end_min <= start_min:
            end_min += week_minutes
        if start_min <= target_min < end_min:
            return entry["title"]
        if start_min <= target_min + week_minutes < end_min:
            return entry["title"]
    return None


def find_show_for_hour(hour_local: datetime, schedule: List[dict]) -> str:
    matches = [item for item in schedule if item["start"] <= hour_local < item["end"]]
    if not matches:
        weekly = find_show_weekly(hour_local, schedule)
        return weekly or "Unknown Program"
    matches.sort(key=lambda item: item["start"], reverse=True)
    return matches[0]["title"] or "Unknown Program"


def build_hourly_entries(
    days: int,
    schedule: List[dict],
    now_utc: Optional[datetime] = None,
) -> List[dict]:
    total_hours = max(days, 1) * 24
    now_utc = now_utc or datetime.now(timezone.utc)
    base_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    timezone_local = ZoneInfo(config.station_timezone)

    entries = []
    for offset in range(1, total_hours + 1):
        hour_utc = base_hour - timedelta(hours=offset)
        hour_local = hour_utc.astimezone(timezone_local)
        file_name = hour_utc.strftime("%Y_%m_%d_%H")
        program_datetime = hour_local.strftime("%Y_%m_%d_%I_%M_%p")
        program_name = sanitize_filename(find_show_for_hour(hour_local, schedule))
        entries.append(
            {
                "file_name": file_name,
                "program_name": program_name or "Unknown Program",
                "program_datetime": program_datetime,
            }
        )
    return entries


def fetch_playlist(
    file_name: str,
    session: requests.Session,
    cache_dir: str,
    offline: bool,
) -> Optional[str]:
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
    response = session.get(
        playlist_url,
        headers={"User-Agent": config.user_agent},
        timeout=config.request_timeout_seconds,
    )
    if response.status_code != 200:
        logger.warning(
            "Playlist not available: %s (status %s)", playlist_url, response.status_code
        )
        return None
    with open(cache_path, "w", encoding="utf-8") as payload:
        payload.write(response.text)
    return response.text


def parse_playlist(playlist_text: str, base_url: str) -> List[str]:
    lines = [line.strip() for line in playlist_text.splitlines() if line.strip()]
    segment_paths = [line for line in lines if not line.startswith("#")]
    return [urljoin(base_url, segment) for segment in segment_paths]


def fetch_segment(
    segment_url: str,
    cache_path: str,
    session: requests.Session,
    offline: bool,
) -> Optional[str]:
    if os.path.exists(cache_path):
        return cache_path
    if offline:
        logger.warning("Offline mode enabled and missing segment cache: %s", cache_path)
        return None
    response = session.get(
        segment_url,
        headers={"User-Agent": config.user_agent},
        timeout=config.request_timeout_seconds,
        stream=True,
    )
    response.raise_for_status()
    ensure_directory(os.path.dirname(cache_path))
    with open(cache_path, "wb") as cache_file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                cache_file.write(chunk)
    return cache_path


def download_segments(
    segment_urls: List[str],
    destination_path: str,
    cache_segments_dir: str,
    session: requests.Session,
    offline: bool,
) -> bool:
    ensure_directory(cache_segments_dir)
    total_segments = len(segment_urls)
    with open(destination_path, "wb") as output_file:
        for index, segment_url in enumerate(segment_urls, start=1):
            if index == 1 or index % 25 == 0 or index == total_segments:
                logger.info("Segment progress: %s/%s", index, total_segments)
            segment_name = os.path.basename(urlparse(segment_url).path)
            cache_path = os.path.join(cache_segments_dir, segment_name)
            cached_segment = fetch_segment(segment_url, cache_path, session, offline)
            if not cached_segment:
                return False
            with open(cached_segment, "rb") as segment_file:
                shutil.copyfileobj(segment_file, output_file, length=1024 * 1024)
    return True


def iter_archive_hours(start_local: datetime, end_local: datetime) -> List[datetime]:
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    current = start_utc.replace(minute=0, second=0, microsecond=0)
    hours = []
    while current < end_utc:
        hours.append(current)
        current += timedelta(hours=1)
    return hours


def append_segments(
    segment_urls: List[str],
    output_handle,
    cache_segments_dir: str,
    session: requests.Session,
    offline: bool,
) -> bool:
    ensure_directory(cache_segments_dir)
    total_segments = len(segment_urls)
    for index, segment_url in enumerate(segment_urls, start=1):
        if index == 1 or index % 25 == 0 or index == total_segments:
            logger.info("Segment progress: %s/%s", index, total_segments)
        segment_name = os.path.basename(urlparse(segment_url).path)
        cache_path = os.path.join(cache_segments_dir, segment_name)
        cached_segment = fetch_segment(segment_url, cache_path, session, offline)
        if not cached_segment:
            return False
        with open(cached_segment, "rb") as segment_file:
            shutil.copyfileobj(segment_file, output_handle, length=1024 * 1024)
    return True


def save_playlist_file(destination_path: str, playlist_text: str) -> None:
    with open(destination_path, "w", encoding="utf-8") as playlist_file:
        playlist_file.write(playlist_text)


def transcode_to_mp3(source_path: str, destination_path: str) -> bool:
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


def fetch_and_process_whrb_archive(
    days: int,
    limit: Optional[int],
    dry_run: bool,
    output_dir: str,
    cache_dir: str,
    offline: bool,
) -> None:
    session = requests.Session()
    timezone_local = ZoneInfo(config.station_timezone)
    now_utc = datetime.now(timezone.utc)
    range_end = now_utc.astimezone(timezone_local)
    range_start = range_end - timedelta(days=max(days, 1))

    logger.info("Archive range: %s to %s", range_start, range_end)
    schedule_ical = fetch_program_schedule_calendar(session, cache_dir, offline)
    show_blocks: List[dict] = []
    if schedule_ical:
        raw_blocks = expand_calendar_events(schedule_ical, range_start, range_end)
        show_blocks = build_show_blocks(days, raw_blocks, now_utc)

    if not show_blocks:
        logger.warning("Falling back to WHRB schedule API for show names.")
        schedule_raw = fetch_schedule(
            session,
            cache_dir,
            offline,
            int(now_utc.timestamp()),
        )
        schedule = normalize_schedule(schedule_raw)
        entries = build_hourly_entries(days, schedule)
        if limit:
            entries = entries[:limit]
        logger.info("Hourly entries to process: %s", len(entries))
        for entry in entries:
            program_name = entry["program_name"]
            program_datetime = entry["program_datetime"]
            file_name = entry["file_name"]

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

            if os.path.exists(output_path):
                logger.info("Skipping existing archive: %s", output_path)
                continue

            playlist_text = fetch_playlist(file_name, session, cache_dir, offline)
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
            logger.info(
                "Downloading %s segments for %s", len(segment_urls), temp_ts_path
            )
            success = download_segments(
                segment_urls, temp_ts_path, cache_segments_dir, session, offline
            )
            if not success:
                logger.warning("Incomplete download for %s", output_path)
                continue
            if config.archive_extension.lower() == "mp3":
                logger.info("Transcoding to MP3: %s", output_path)
                if not transcode_to_mp3(temp_ts_path, output_path):
                    if temp_ts_path != output_path and os.path.exists(temp_ts_path):
                        os.remove(temp_ts_path)
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    continue
                if temp_ts_path != output_path:
                    os.remove(temp_ts_path)
                notify_discord_on_success(output_path)
            if config.save_playlist_file:
                save_playlist_file(playlist_path, playlist_text)
            elif os.path.exists(playlist_path):
                os.remove(playlist_path)
        return

    if limit:
        show_blocks = show_blocks[:limit]

    logger.info("Show blocks to process: %s", len(show_blocks))
    for block in show_blocks:
        program_name = block["title"] or "Unknown Program"
        start_local = block["start"]
        end_local = block["end"]
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

        if os.path.exists(output_path):
            logger.info("Skipping existing archive: %s", output_path)
            continue

        if dry_run:
            logger.info("Dry run: would download %s", output_path)
            continue

        logger.info(
            "Processing block: %s (%s to %s)",
            program_name,
            start_local,
            end_local,
        )
        hours = iter_archive_hours(start_local, end_local)
        if not hours:
            continue

        has_content = False
        seen_hours: set[str] = set()
        with open(temp_ts_path, "wb") as output_file:
            for hour_utc in hours:
                file_name = hour_utc.strftime("%Y_%m_%d_%H")
                if file_name in seen_hours:
                    logger.info("Skipping duplicate hour %s", file_name)
                    continue
                seen_hours.add(file_name)
                # Convert the UTC hour back to local for clearer logging so it's
                # obvious what local program hour is being appended.
                hour_local_for_log = hour_utc.astimezone(timezone_local)
                hour_local_label = hour_local_for_log.strftime("%Y_%m_%d_%I_%M_%p")
                logger.info(
                    "Appending hour %s (UTC) -> %s (local) to %s",
                    file_name,
                    hour_local_label,
                    temp_ts_path,
                )
                playlist_text = fetch_playlist(file_name, session, cache_dir, offline)
                if not playlist_text:
                    continue
                base_url = f"{config.base_archive_url}/{file_name}/"
                segment_urls = parse_playlist(playlist_text, base_url)
                if not segment_urls:
                    continue
                cache_segments_dir = os.path.join(cache_dir, file_name, "segments")
                logger.info(
                    "Appending %s segments for %s", len(segment_urls), temp_ts_path
                )
                if not append_segments(
                    segment_urls, output_file, cache_segments_dir, session, offline
                ):
                    logger.warning("Incomplete download for %s", output_path)
                    continue
                has_content = True

        if not has_content:
            if os.path.exists(temp_ts_path):
                os.remove(temp_ts_path)
            continue

        if config.archive_extension.lower() == "mp3":
            logger.info("Transcoding to MP3: %s", output_path)
            if not transcode_to_mp3(temp_ts_path, output_path):
                if temp_ts_path != output_path and os.path.exists(temp_ts_path):
                    os.remove(temp_ts_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
                continue
            if temp_ts_path != output_path:
                os.remove(temp_ts_path)
            notify_discord_on_success(output_path)

        if os.path.exists(playlist_path):
            os.remove(playlist_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download WHRB stream archive segments."
    )
    parser.add_argument(
        "--days", type=int, default=config.archive_days, help="Days of archive to scan."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of hours to download."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Only log what would be downloaded."
    )
    parser.add_argument(
        "--output-dir",
        default=config.output_dir,
        help="Directory for saved recordings.",
    )
    parser.add_argument(
        "--cache-dir", default=config.cache_dir, help="Directory for cached requests."
    )
    parser.add_argument(
        "--offline", action="store_true", help="Use cached data only, no network."
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)
    cache_dir = os.path.abspath(args.cache_dir)
    ensure_directory(cache_dir)
    fetch_and_process_whrb_archive(
        args.days,
        args.limit,
        args.dry_run,
        output_dir,
        cache_dir,
        args.offline,
    )


if __name__ == "__main__":
    main()
