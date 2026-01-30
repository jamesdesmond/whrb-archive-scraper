# WHRB Stream Archive Downloader

Download WHRB's two-week stream archive into per-program folders. The script groups multi-hour shows into a single file, caches HLS segments locally, and transcodes to MP3 by default.

## Features

- Scrapes the WHRB program schedule page to discover the Google Calendar feed.
- Builds show blocks for the last 14 days (configurable).
- **Skips in-progress shows** and any blocks that would be partial.
- Groups hourly HLS archives into a single file per show block.
- Caches schedules, playlists, and segments to minimize repeat downloads.
- Optional Discord notification when an MP3 is successfully created.

## Output layout

Each show block is saved as:

```
{output_dir}/{program_name}/{program_name}_{program_start_local}.mp3
```

Playlists are **not** saved by default (`save_playlist_file = False`).

## Configuration

Edit `config.py` as needed:

- `output_dir`: destination for recordings
- `cache_dir`: cache for schedule/playlists/segments
- `archive_days`: number of days to scan (default 14)
- `archive_extension`: default `mp3`
- `ffmpeg_path`: ffmpeg executable (override with `FFMPEG_PATH`)
- `program_schedule_url`: schedule page used to locate the calendar feed
- `station_timezone`: used for timestamps

Environment variables:

- `FFMPEG_PATH`: overrides `ffmpeg_path`
- `DISCORD_WEBHOOK_URL`: send a Discord message **only when an MP3 is created**

## Usage

Run the downloader:

```bash
python main.py
```

Limit or preview:

```bash
python main.py --limit 3 --dry-run
```

### Caching & offline runs

The downloader caches schedule data, playlists, and HLS segments in `cache_dir`. If cached data exists, it will be reused automatically.

Offline mode uses cached data only:

```bash
python main.py --offline --limit 3
```

Override output or cache directories:

```bash
python main.py --output-dir ./recordings --cache-dir ./cache
```

## Tests

```bash
python -m unittest
```
