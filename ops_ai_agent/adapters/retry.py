"""一時的エラーに対する指数バックオフ再試行（アダプタ共通）。"""

import random
import time
from collections.abc import Callable

_BASE_DELAY = 0.5


def call_with_retry[T](
    fn: Callable[[], T],
    *,
    max_retries: int,
    retryable: Callable[[Exception], bool],
    sleeper: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """fn を実行し、retryable な例外のみ指数バックオフで再試行する。

    試行は最大 max_retries + 1 回。discharge した例外はそのまま送出する。
    遅延は 0.5 * 2^attempt の等値ジッター（指数値の 50%〜100%）。
    """
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if not retryable(exc) or attempt >= max_retries:
                raise
            full_delay = _BASE_DELAY * (2**attempt)
            sleeper(full_delay * (0.5 + 0.5 * jitter()))
    raise RuntimeError("到達不能: 再試行ループを抜けました")  # pragma: no cover
