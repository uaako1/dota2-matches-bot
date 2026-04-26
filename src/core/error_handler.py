from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class APIError(Exception):
    pass


class RetryableError(APIError):
    pass


class PermanentError(APIError):
    pass


def retry_on_error(max_retries: int = 3, backoff_seconds: float = 1.0):
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except RetryableError:
                    if attempt >= max_retries:
                        raise
                    await asyncio.sleep(backoff_seconds * attempt)
                except PermanentError:
                    raise
                except Exception as exc:
                    logger.exception("Unexpected error in %s: %s", func.__name__, exc)
                    raise
            raise RuntimeError("retry loop exhausted")

        return wrapper

    return decorator


def graceful_fallback(default: T):
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                logger.warning("Fallback in %s due to %s", func.__name__, exc)
                return default

        return wrapper

    return decorator
