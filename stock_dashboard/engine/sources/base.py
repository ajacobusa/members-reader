"""Shared HTTP helper for data-source providers. Fails soft (returns None).

Quota-aware: when a process-wide QuotaGuard is configured, calls to a provider
that is currently rate-limited are skipped before the request, and any response
that signals exhaustion (HTTP 429 or a 'limit reached' body) marks that provider
as cooling so the rest of its quota is preserved."""
import logging
from typing import Any, Optional

from stock_dashboard.engine import ratelimit

log = logging.getLogger(__name__)


def http_get_json(url: str, params: Optional[dict] = None,
                  headers: Optional[dict] = None, timeout: int = 8) -> Optional[Any]:
    """GET and parse JSON. Returns None on any error / non-200 (graceful)."""
    guard = ratelimit.get_guard()
    provider = ratelimit.provider_for_url(url)
    if guard and provider and guard.is_cooling(provider):
        log.info("skip GET %s — provider %s is rate-limited (cooling)", url, provider)
        return None
    try:
        import requests
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        if r.status_code != 200:
            log.warning("GET %s -> HTTP %s", url, r.status_code)
            if guard and provider and ratelimit.detect(r.status_code, None):
                retry_after = r.headers.get("Retry-After") if hasattr(r, "headers") else None
                guard.mark(provider, retry_after=_as_float(retry_after),
                           reason=f"HTTP {r.status_code}")
            return None
        data = r.json()
        if guard and provider and ratelimit.detect(200, data):
            guard.mark(provider, reason="quota notice in 200 body")
            return None
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("GET %s failed: %s", url, exc)
        return None


def _as_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
