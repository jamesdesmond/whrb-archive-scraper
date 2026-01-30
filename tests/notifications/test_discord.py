from dataclasses import replace
from unittest import mock

import requests

from whrb_archive.config import load_config
from whrb_archive.notifications.discord import (
    DiscordWebhookHandler,
    notify_discord_on_success,
)


def test_notify_discord_on_success_posts():
    base_config = load_config()
    config = replace(base_config, webhook_url="https://discord.test/webhook")
    with mock.patch("requests.Session.post") as mock_post:
        notify_discord_on_success("/tmp/test.mp3", config)
    mock_post.assert_called_once()


def test_discord_handler_handles_request_exception():
    handler = DiscordWebhookHandler("https://discord.test/webhook")
    record = mock.Mock()
    record.__dict__["msg"] = "hi"
    record.__dict__["args"] = ()
    handler.setFormatter(mock.Mock(format=lambda _: "hello"))
    with mock.patch("requests.Session.post", side_effect=requests.RequestException):
        handler.emit(record)
