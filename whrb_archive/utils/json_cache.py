"""JSON cache helpers for schedule data."""

from __future__ import annotations

import json
import os
from typing import List

from .filesystem import ensure_directory


def read_json(path: str) -> List[dict]:
    """Read JSON data from disk."""
    with open(path, "r", encoding="utf-8") as payload:
        return json.load(payload)


def write_json(path: str, data: List[dict]) -> None:
    """Write JSON data to disk, creating the parent directory if needed."""
    ensure_directory(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as payload:
        json.dump(data, payload)
