"""Discord webhook notifications."""

from __future__ import annotations

import logging

import requests

from ..models.archive import ArchiveConfig

logger = logging.getLogger("whrb-archive")


class DiscordWebhookHandler(logging.Handler):
    """Logging handler that posts log lines to a Discord webhook."""

    def __init__(self, webhook_url: str, timeout: int = 10) -> None:
        super().__init__()
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.session = requests.Session()

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        if not message:
            return
        try:
            self.session.post(
                self.webhook_url,
                json={"content": message},
                timeout=self.timeout,
            )
        except requests.RequestException:
            return


def notify_discord_on_success(path: str, config: ArchiveConfig) -> None:
    """Send a Discord notification for a completed MP3 download."""
    if not config.webhook_url:
        return
    handler = DiscordWebhookHandler(
        config.webhook_url,
        timeout=config.request_timeout_seconds,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        name="whrb-archive",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=f"MP3 created: {path}",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
