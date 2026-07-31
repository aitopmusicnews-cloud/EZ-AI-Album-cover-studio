from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    base_delay_seconds: float,
    on_attempt: Callable[[int, str, Exception | None], None],
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        on_attempt(attempt, "started", None)
        try:
            result = await operation()
            on_attempt(attempt, "succeeded", None)
            return result
        except Exception as exc:  # the retry decision is based on a typed retryable attribute
            last_error = exc
            on_attempt(attempt, "failed", exc)
            retryable = bool(getattr(exc, "retryable", False))
            if not retryable or attempt >= max_attempts:
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1))
            if delay > 0:
                await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error
