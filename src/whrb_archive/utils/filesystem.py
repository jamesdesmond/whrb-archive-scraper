"""Filesystem helpers for archive operations."""

from __future__ import annotations

import os
import re


def sanitize_filename(filename: str) -> str:
    """Sanitize a string for filesystem-safe filenames."""
    invalid_chars = r"[\\/:*?\"<>|\x00-\x1F\x7F]"
    return re.sub(invalid_chars, "", filename).strip()


def normalize_show_title(title: str) -> str:
    """Normalize show titles for consistent folder naming."""
    cleaned = sanitize_filename(title)
    if cleaned.lower().startswith("the "):
        cleaned = cleaned[4:]
    return cleaned.strip()


def ensure_directory(path: str) -> None:
    """Create a directory if it does not already exist."""
    os.makedirs(path, exist_ok=True)
