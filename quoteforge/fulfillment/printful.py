"""Printful fulfillment adapter (stdlib HTTP).

Creates a Printful order via the v1 API when PRINTFUL_API_KEY is set; otherwise
returns a 'manual' result so the order is flagged for hand-fulfillment. Never
raises - fulfillment errors are returned, not thrown.
"""
from __future__ import annotations

import json
import urllib.request


def create_order(order_id: str, recipient: dict, artwork_url: str,
                 variant_id, **kwargs) -> dict:
    """Submit a print order to Printful (mocked in TEST_MODE)."""
    from quoteforge.config import PRINTFUL_API_KEY, TEST_MODE
    if TEST_MODE or not PRINTFUL_API_KEY:
        return {"status": "manual", "vendor": "printful",
                "detail": "no Printful key / TEST_MODE - fulfill manually",
                "id": ""}
    body = json.dumps({
        "external_id": order_id,
        "recipient": recipient,
        "items": [{"variant_id": variant_id, "quantity": kwargs.get("quantity", 1),
                   "files": [{"url": artwork_url}]}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.printful.com/orders", data=body, method="POST",
        headers={"Authorization": f"Bearer {PRINTFUL_API_KEY}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {"status": "submitted", "vendor": "printful",
                "id": str(data.get("result", {}).get("id", ""))}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "vendor": "printful", "detail": str(exc), "id": ""}


# Printful's "fulfilled" means every item has shipped.
_STATUS_MAP = {"fulfilled": "shipped", "partial": "shipped"}


def get_order_status(printful_order_id: str) -> dict:
    """Poll Printful for order status + tracking (mocked in TEST_MODE).

    Normalized to the same shape gelato_api.get_gelato_order_status returns,
    so the fulfillment tracker can treat every vendor identically.
    """
    from quoteforge.config import PRINTFUL_API_KEY, TEST_MODE
    from quoteforge.fulfillment.vendor_http import (first_tracked_shipment,
                                                    get_json)
    if TEST_MODE or not PRINTFUL_API_KEY:
        return {"mock": True, "vendor": "printful", "status": "unknown",
                "tracking_number": "", "tracking_url": "", "carrier": ""}
    data = get_json(f"https://api.printful.com/orders/{printful_order_id}",
                    PRINTFUL_API_KEY)
    result = data.get("result", {}) or {}
    raw = (result.get("status") or "unknown").lower()
    shipment = first_tracked_shipment(result.get("shipments"),
                                      "tracking_number")
    return {
        "vendor": "printful",
        "status": _STATUS_MAP.get(raw, raw),
        "tracking_number": shipment.get("tracking_number", ""),
        "tracking_url": shipment.get("tracking_url", ""),
        "carrier": shipment.get("carrier", ""),
        "raw": result,
    }


def verify_printful_auth() -> dict:
    """Live check that PRINTFUL_API_KEY is valid (no order created)."""
    from quoteforge.config import PRINTFUL_API_KEY
    from quoteforge.fulfillment.vendor_http import verify_auth
    if not PRINTFUL_API_KEY:
        return {"ok": False, "detail": "PRINTFUL_API_KEY not set"}
    return verify_auth("https://api.printful.com/orders?limit=1",
                       PRINTFUL_API_KEY, "authenticated (orders reachable)")
