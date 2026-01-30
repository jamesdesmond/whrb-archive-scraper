"""Retry helpers with exponential backoff."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior."""

    attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0


def retry(
    operation: Callable[[], T],
    *,
    config: RetryConfig,
    retry_on: Iterable[type[Exception]],
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run an operation with retry/backoff.

    Args:
        operation: Callable to invoke.
        config: Retry parameters.
        retry_on: Exception types to retry.
        sleep: Sleep function for testability.

    Raises:
        Exception: The last exception raised if retries are exhausted.
    """
    attempt = 0
    while True:
        try:
            return operation()
        except tuple(retry_on):  # type: ignore[arg-type]
            attempt += 1
            if attempt >= config.attempts:
                raise
            delay = min(
                config.base_delay_seconds * (2 ** (attempt - 1)),
                config.max_delay_seconds,
            )
            sleep(delay)
