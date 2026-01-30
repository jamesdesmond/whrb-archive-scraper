"""Logging configuration for the downloader."""

from __future__ import annotations

import logging


def configure_logging() -> None:
    """Configure root logging for the downloader.

    Adds a default stream handler and sets INFO-level logging.
    """
    logger_root = logging.getLogger()
    logger_root.setLevel(logging.INFO)

    stream_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(stream_format)
    logger_root.addHandler(stream_handler)

    logger_root.info("Script Startup")
