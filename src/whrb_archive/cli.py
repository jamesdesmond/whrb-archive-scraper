"""Command-line interface for the WHRB archive downloader."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import load_config
from .errors import ArchiveError
from .services.archive_service import fetch_and_process_whrb_archive
from .utils.filesystem import ensure_directory
from .utils.logging_utils import configure_logging


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argparse namespace containing CLI options.
    """
    config = load_config()
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
        "--cache-dir",
        default=config.cache_dir,
        help="Directory for cached requests (omit to disable caching).",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Use cached data only, no network."
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the downloader.

    Loads configuration, ensures cache directories exist, and triggers the
    archive download workflow.
    """
    configure_logging()
    logger = logging.getLogger("whrb-archive")
    args = parse_args()
    config = load_config()
    output_dir = os.path.abspath(args.output_dir)
    cache_dir = os.path.abspath(args.cache_dir) if args.cache_dir else None
    if cache_dir:
        ensure_directory(cache_dir)
    elif args.offline:
        logger.warning(
            "Offline mode requested without a cache directory; "
            "downloads will fail without cached data."
        )
    try:
        fetch_and_process_whrb_archive(
            args.days,
            args.limit,
            args.dry_run,
            output_dir,
            cache_dir,
            args.offline,
            config,
        )
    except ArchiveError as exc:
        logger.error("Download failed: %s", exc)
        sys.exit(2)
