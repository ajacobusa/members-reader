"""Optional error monitoring (Sentry).

A drop-in, zero-overhead hook: when ``SENTRY_DSN`` is set in the environment and
``sentry-sdk`` is installed, unhandled errors in the webhook server and the
admin CLI are captured. With no DSN (the default), every function here is a
no-op — nothing is imported, nothing is sent, no dependency is required.

This is intended for when the app is publicly hosted (the webhook server on a
VPS). For the local single-operator setup it stays dormant.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_initialised = False


def init_monitoring() -> bool:
    """Initialise Sentry if a DSN is configured and the SDK is installed.

    Returns True if monitoring is now active, False otherwise. Safe to call
    multiple times (initialises at most once) and never raises."""
    global _initialised
    if _initialised:
        return True
    try:
        from quoteforge.config import SENTRY_DSN
    except Exception:  # noqa: BLE001
        return False
    if not SENTRY_DSN:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.0,
                        send_default_pii=False)
        _initialised = True
        return True
    except Exception:  # noqa: BLE001 — SDK missing or bad DSN: stay silent
        return False


def capture(exc: BaseException) -> None:
    """Report an exception if monitoring is active; otherwise a no-op."""
    if not _initialised:
        return
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception as cap_exc:  # noqa: BLE001 - monitoring must never raise
        logger.debug("sentry capture failed: %s", cap_exc)
