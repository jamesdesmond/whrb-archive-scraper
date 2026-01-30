import logging

from whrb_archive.utils.logging_utils import configure_logging


def test_configure_logging_adds_handler():
    root = logging.getLogger()
    root.handlers.clear()
    configure_logging()
    assert root.handlers
