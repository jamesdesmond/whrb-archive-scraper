import sys
from unittest import mock

import pytest

from whrb_archive import cli
from whrb_archive.errors import ArchiveError
from whrb_archive.config import load_config


def test_parse_args_defaults(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])
    args = cli.parse_args()
    config = load_config()
    assert args.days == config.archive_days
    assert args.output_dir == config.output_dir


def test_main_invokes_workflow(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])
    with mock.patch("whrb_archive.cli.fetch_and_process_whrb_archive") as mock_fetch:
        cli.main()
    mock_fetch.assert_called_once()


def test_main_warns_when_offline_without_cache(monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", ["prog", "--offline"])
    with (
        mock.patch("whrb_archive.cli.fetch_and_process_whrb_archive"),
        mock.patch("whrb_archive.cli.load_config") as mock_config,
    ):
        mock_config.return_value = load_config()
        cli.main()
    assert any(
        "Offline mode requested without a cache directory" in message
        for message in caplog.messages
    )


def test_main_exits_on_archive_error(monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", ["prog"])
    with (
        mock.patch(
            "whrb_archive.cli.fetch_and_process_whrb_archive",
            side_effect=ArchiveError("ffmpeg failed"),
        ),
        pytest.raises(SystemExit) as excinfo,
    ):
        cli.main()
    assert excinfo.value.code == 2
    assert any("Download failed" in message for message in caplog.messages)
