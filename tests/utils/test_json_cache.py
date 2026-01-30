import os
import tempfile

from whrb_archive.utils.json_cache import read_json, write_json


def test_read_write_json_roundtrip():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "data.json")
        write_json(path, [{"value": 1}])
        data = read_json(path)
    assert data == [{"value": 1}]
