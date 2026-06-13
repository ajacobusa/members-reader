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
# ONLY "Delivered" confirms receipt. A failed delivery / return-to-sender /
# expired tracking is an EXCEPTION (needs owner attention) - never a silent
# in-transit, and never a delivery.
_AFTERSHIP_MAP = {
    "Delivered": "delivered",
    "InfoReceived": "in_transit", "InTransit": "in_transit",
    "OutForDelivery": "in_transit", "AvailableForPickup": "in_transit",
    "Pending": "in_transit",
    "AttemptFail": "exception", "Exception": "exception", "Expired": "exception",
}


def _configured() -> tuple[str, str]:
    """(api_key, provider) when a tracking API is usable, else ('', '')."""
    from quoteforge.config import (TRACKING_API_KEY, TRACKING_API_PROVIDER,
                                   TEST_MODE)
    if TEST_MODE or not TRACKING_API_KEY:
        return "", ""
    return TRACKING_API_KEY, (TRACKING_API_PROVIDER or "aftership").lower()


def _iso2(country: str) -> str:
    """Best-effort 2-letter country code (handles 'USA'/'United States')."""
    c = (country or "").strip().upper()
    return {"USA": "US", "UNITED STATES": "US", "CAN": "CA", "CANADA": "CA",
            "GBR": "GB", "UNITED KINGDOM": "GB", "AUS": "AU",
            "AUSTRALIA": "AU"}.get(c, c[:2])


def carrier_status(tracking_number: str, carrier: str = "") -> str | None:
    """Normalized carrier state: 'delivered'/'in_transit'/'exception'/None.
    Thin wrapper over carrier_detail (kept for callers that only need status)."""
    return carrier_detail(tracking_number, carrier).get("status")


def carrier_detail(tracking_number: str, carrier: str = "") -> dict:
    """Full carrier detail: {status, delivered_country, delivered_state,
    estimated_delivery}. status is None when not configured / no usable scan."""
    blank = {"status": None, "delivered_country": "", "delivered_state": "",
             "estimated_delivery": ""}
    key, provider = _configured()
    if not (key and tracking_number):
        return blank
    try:
        if provider == "aftership":
            return _aftership_detail(tracking_number, carrier, key)
        return {**blank, "status": _seventeentrack_status(tracking_number, key)}
    except Exception:  # noqa: BLE001
        return blank       # carrier API hiccup -> let the caller fall back


def _aftership_detail(tn: str, carrier: str, key: str) -> dict:
    """Query AfterShip; return status + the delivered checkpoint's location."""
    url = f"https://api.aftership.com/v4/trackings/{carrier or 'auto'}/{tn}"
    req = urllib.request.Request(url, headers={"aftership-api-key": key})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    trk = ((data.get("data") or {}).get("tracking") or {})
    status = _AFTERSHIP_MAP.get(trk.get("tag") or "")
    dc = ds = ""
    if status == "delivered":
        # Prefer the Delivered checkpoint's location, else the last checkpoint.
        cps = trk.get("checkpoints") or []
        deliv = [c for c in cps if (c.get("tag") or "") == "Delivered"]
        cp = (deliv or cps[-1:] or [{}])[-1]
        dc = _iso2(cp.get("country_iso3") or cp.get("country_name") or "")
        ds = cp.get("state") or ""
    return {"status": status, "delivered_country": dc, "delivered_state": ds,
            "estimated_delivery": trk.get("expected_delivery") or ""}


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
