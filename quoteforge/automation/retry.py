"""Retry with exponential backoff for transient external-API failures.

A single 5xx / timeout from Gelato, Claude, Canva, or Drive should not
permanently fail an order. This wraps a call and retries on transient errors.
"""
import time
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP status codes worth retrying (transient server/rate-limit errors)
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def is_transient(exc: Exception) -> bool:
    """Heuristic: is this exception worth retrying?"""
    # requests.HTTPError exposes .response.status_code
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in TRANSIENT_STATUS:
        return True
    # connection/timeout errors are transient
    name = type(exc).__name__.lower()
    return any(k in name for k in ("timeout", "connection", "temporarilyunavailable"))


def retry_call(
    func: Callable[..., T],
    *args,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    **kwargs,
) -> T:
    """Call func(*args, **kwargs), retrying transient failures with backoff.

    Delays: base_delay, base_delay*2, base_delay*4, ...
    Non-transient errors are raised immediately (no point retrying a 400).
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts or not is_transient(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"Transient error on attempt {attempt}/{max_attempts} "
                f"({type(exc).__name__}): retrying in {delay}s"
            )
            time.sleep(delay)
    # unreachable, but satisfies type checker
    raise last_exc  # type: ignore[misc]
