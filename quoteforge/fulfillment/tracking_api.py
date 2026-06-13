"""Carrier tracking-API client (AfterShip / 17track) - confirms REAL delivery.

Printify/Printful order APIs never report delivery, so without this the system
ASSUMES delivery after a timer. When TRACKING_API_KEY is configured, this polls
the carrier (via the aggregator) for an actual delivered scan, so delivery is
CONFIRMED rather than assumed. Disabled (returns None) when no key is set or in
TEST_MODE - the tracker then falls back to the timer assumption.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

# Aggregator status -> our normalized state.
_AFTERSHIP_MAP = {
    "Delivered": "delivered",
    "InfoReceived": "in_transit", "InTransit": "in_transit",
    "OutForDelivery": "in_transit", "AvailableForPickup": "in_transit",
    "AttemptFail": "in_transit", "Pending": "in_transit",
    "Exception": "exception", "Expired": "exception",
}


def _configured() -> tuple[str, str]:
    """(api_key, provider) when a tracking API is usable, else ('', '')."""
    from quoteforge.config import (TRACKING_API_KEY, TRACKING_API_PROVIDER,
                                   TEST_MODE)
    if TEST_MODE or not TRACKING_API_KEY:
        return "", ""
    return TRACKING_API_KEY, (TRACKING_API_PROVIDER or "aftership").lower()


def carrier_status(tracking_number: str, carrier: str = "") -> str | None:
    """Normalized carrier state for a tracking number: 'delivered',
    'in_transit', 'exception', or None (unknown / not configured / no scan).

    None means "the carrier told us nothing usable" - the caller should fall
    back to its timer assumption rather than treat None as not-delivered.
    """
    key, provider = _configured()
    if not (key and tracking_number):
        return None
    try:
        if provider == "aftership":
            return _aftership_status(tracking_number, carrier, key)
        return _seventeentrack_status(tracking_number, key)
    except Exception:  # noqa: BLE001
        return None        # carrier API hiccup -> let the caller fall back


def _aftership_status(tn: str, carrier: str, key: str) -> str | None:
    """Query AfterShip for a tracking number's latest tag."""
    url = f"https://api.aftership.com/v4/trackings/{carrier or 'auto'}/{tn}"
    req = urllib.request.Request(url, headers={"aftership-api-key": key})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = (((data.get("data") or {}).get("tracking") or {}).get("tag")) or ""
    return _AFTERSHIP_MAP.get(tag)


def _seventeentrack_status(tn: str, key: str) -> str | None:
    """Query 17track for a tracking number's latest status."""
    req = urllib.request.Request(
        "https://api.17track.net/track/v2.2/gettrackinfo",
        data=json.dumps([{"number": tn}]).encode("utf-8"),
        headers={"17token": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    accepted = (((data.get("data") or {}).get("accepted")) or [])
    if not accepted:
        return None
    # 17track latest_status.status: "Delivered" / "InTransit" / ...
    status = (((accepted[0].get("track_info") or {}).get("latest_status") or {})
              .get("status")) or ""
    return {"Delivered": "delivered", "InTransit": "in_transit",
            "Exception": "exception"}.get(status, "in_transit" if status else None)
