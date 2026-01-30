from unittest import mock

import pytest

from whrb_archive.utils.retry import RetryConfig, retry


def test_retry_succeeds_after_failure():
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] < 2:
            raise ValueError("fail")
        return "ok"

    result = retry(
        operation,
        config=RetryConfig(attempts=3, base_delay_seconds=0.0, max_delay_seconds=0.0),
        retry_on=(ValueError,),
        sleep=lambda _: None,
    )
    assert result == "ok"


def test_retry_raises_after_exhausted():
    def operation():
        raise ValueError("fail")

    with pytest.raises(ValueError):
        retry(
            operation,
            config=RetryConfig(
                attempts=2, base_delay_seconds=0.0, max_delay_seconds=0.0
            ),
            retry_on=(ValueError,),
            sleep=lambda _: None,
        )


def test_retry_sleep_called():
    sleep = mock.Mock()

    def operation():
        raise ValueError("fail")

    with pytest.raises(ValueError):
        retry(
            operation,
            config=RetryConfig(
                attempts=2, base_delay_seconds=1.0, max_delay_seconds=1.0
            ),
            retry_on=(ValueError,),
            sleep=sleep,
        )
    sleep.assert_called_once_with(1.0)
