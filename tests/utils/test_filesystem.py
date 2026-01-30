import os
import tempfile

from whrb_archive.utils.filesystem import ensure_directory, sanitize_filename


def test_sanitize_filename_removes_invalid_chars():
    assert sanitize_filename("Bad/Name:*") == "BadName"


def test_ensure_directory_creates_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        target = os.path.join(temp_dir, "nested")
        ensure_directory(target)
        assert os.path.isdir(target)
