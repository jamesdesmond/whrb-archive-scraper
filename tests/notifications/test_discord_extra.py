import logging

from whrb_archive.config import load_config
from whrb_archive.notifications.discord import (
    DiscordWebhookHandler,
    notify_discord_on_success,
)


def test_notify_discord_on_success_no_webhook():
    config = load_config()
    notify_discord_on_success("/tmp/test.mp3", config)


def test_discord_handler_ignores_empty_message():
    handler = DiscordWebhookHandler("https://discord.test/webhook")
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
