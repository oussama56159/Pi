from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int = 5,
    base_delay_s: float = 0.25,
    max_delay_s: float = 5.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry an async operation with exponential backoff and jitter."""
    attempt = 0
    while True:
        try:
            return await operation()
        except retry_on:
            attempt += 1
            if attempt > retries:
                raise
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.2)
            await asyncio.sleep(delay)

