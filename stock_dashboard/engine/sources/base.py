"""Shared HTTP helper for data-source providers. Fails soft (returns None)."""
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


def http_get_json(url: str, params: Optional[dict] = None,
                  headers: Optional[dict] = None, timeout: int = 8) -> Optional[Any]:
    """GET and parse JSON. Returns None on any error / non-200 (graceful)."""
    try:
        import requests
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        if r.status_code != 200:
            log.warning("GET %s -> HTTP %s", url, r.status_code)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("GET %s failed: %s", url, exc)
        return None
