import sys
from unittest import mock

from whrb_archive import cli
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
