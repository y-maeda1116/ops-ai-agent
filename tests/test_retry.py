"""call_with_retry（指数バックオフ再試行）のテスト。"""

import pytest

from ops_ai_agent.adapters.retry import call_with_retry


class TransientError(Exception):
    """リトライ対象の擬似エラー。"""


class PermanentError(Exception):
    """リトライ対象外の擬似エラー。"""


def _flaky(calls: list[int], fail_times: int):
    def fn() -> str:
        calls.append(1)
        if len(calls) <= fail_times:
            raise TransientError("transient")
        return "ok"

    return fn


def test_returns_after_transient_failures():
    calls: list[int] = []
    result = call_with_retry(
        _flaky(calls, fail_times=2),
        max_retries=2,
        retryable=lambda _exc: True,
        sleeper=lambda _s: None,
    )
    assert result == "ok"
    assert len(calls) == 3


def test_raises_after_exhausting_retries():
    calls: list[int] = []
    with pytest.raises(TransientError):
        call_with_retry(
            _flaky(calls, fail_times=99),
            max_retries=2,
            retryable=lambda _exc: True,
            sleeper=lambda _s: None,
        )
    assert len(calls) == 3  # 初回 + リトライ2回


def test_non_retryable_raises_immediately():
    calls: list[int] = []

    def fail_permanently() -> str:
        calls.append(1)
        raise PermanentError("permanent")

    with pytest.raises(PermanentError):
        call_with_retry(
            fail_permanently,
            max_retries=2,
            retryable=lambda exc: isinstance(exc, TransientError),
            sleeper=lambda _s: None,
        )
    assert len(calls) == 1


def test_backoff_is_exponential_with_jitter():
    delays: list[float] = []

    def fake_jitter() -> float:
        return 0.0  # ジッター下限（指数値の半分）

    def fail_forever() -> str:
        raise TransientError("transient")

    with pytest.raises(TransientError):
        call_with_retry(
            fail_forever,
            max_retries=3,
            retryable=lambda _exc: True,
            sleeper=delays.append,
            jitter=fake_jitter,
        )
    # 0.5 * 2^0 / 2 = 0.25, 0.5 * 2^1 / 2 = 0.5, 0.5 * 2^2 / 2 = 1.0
    assert delays == pytest.approx([0.25, 0.5, 1.0])


def test_jitter_upper_bound():
    delays: list[float] = []

    def fake_jitter() -> float:
        return 1.0  # ジッター上限（指数値ちょうど）

    def fail_forever() -> str:
        raise TransientError("transient")

    with pytest.raises(TransientError):
        call_with_retry(
            fail_forever,
            max_retries=1,
            retryable=lambda _exc: True,
            sleeper=delays.append,
            jitter=fake_jitter,
        )
    assert delays == pytest.approx([0.5])
