# WHRB Stream Archive Downloader

Automatically download and archive WHRB radio programs. Run this script daily to capture all available shows from WHRB's public archive (limited to the last 14 days by FCC regulation) and save them as MP3 files organized by program name.

## What you get

- **Complete episode recordings** organized in per-program folders
- **Automatic multi-hour show handling** — long programs are saved as a single file
- **Smart skip logic** — already-downloaded shows and in-progress broadcasts are skipped
- **MP3 output** ready for playback or archival
- **Optional Discord notifications** when new recordings are saved

## How it works

The script runs on-demand or via a daily cron job / scheduled task. Each run:

1. Checks WHRB's program schedule for the last 14 days
2. Downloads any complete shows not already saved
3. Skips in-progress shows (they'll be captured on the next run)
4. Saves recordings as `{program_name}/{program_name}_{date_time}.mp3`

## Requirements

- Python 3.10+
- `ffmpeg` installed and in PATH (or set `FFMPEG_PATH` environment variable)

## Quick start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the downloader:

```bash
python main.py
```

Configure output and cache directories:

```bash
python main.py --output-dir ./recordings --cache-dir ./cache
```

Set up for scheduled daily runs:

```bash
#!/bin/bash
export DISCORD_WEBHOOK_URL="your_webhook_url_here"  # optional

cd /path/to/whrb-archive-scraper
python main.py --output-dir ./recordings --cache-dir ./cache
```

## Configuration

Edit `config.py` or use command-line arguments:

- `--output-dir`: where to save recordings (default: `./recordings`)
- `--cache-dir`: where to store temporary data (default: `./cache`)
- `--days`: how many days to scan (default: 14, the FCC maximum)

Optional environment variables:

- `FFMPEG_PATH`: path to ffmpeg executable
- `DISCORD_WEBHOOK_URL`: receive a notification when each MP3 is saved

## Developer notes

### Caching

The script caches schedule data and audio segments to avoid redundant downloads during testing and development. Cached data is reused automatically.

Run in offline mode (uses only cached data):

```bash
python main.py --offline
```

### Tests

```bash
python -m unittest
```
