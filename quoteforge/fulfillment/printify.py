"""Printify fulfillment adapter (stdlib HTTP).

Submits a Printify order when PRINTIFY_API_KEY + PRINTIFY_SHOP_ID are set;
otherwise returns a 'manual' result. Never raises.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def create_order(order_id: str, recipient: dict, artwork_url: str,
                 blueprint=None, **kwargs) -> dict:
    """Submit a print order to Printify (mocked in TEST_MODE)."""
    from quoteforge.config import PRINTIFY_API_KEY, PRINTIFY_SHOP_ID, TEST_MODE
    if TEST_MODE or not (PRINTIFY_API_KEY and PRINTIFY_SHOP_ID):
        return {"status": "manual", "vendor": "printify",
                "detail": "no Printify key/shop / TEST_MODE - fulfill manually",
                "id": ""}
    body = json.dumps({
        "external_id": order_id, "label": order_id,
        "line_items": kwargs.get("line_items", []),
        "address_to": recipient,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.printify.com/v1/shops/{PRINTIFY_SHOP_ID}/orders.json",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {PRINTIFY_API_KEY}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {"status": "submitted", "vendor": "printify",
                "id": str(data.get("id", ""))}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "vendor": "printify", "detail": str(exc), "id": ""}


# Printify's "fulfilled" means the order has shipped.
_STATUS_MAP = {"fulfilled": "shipped", "partially-fulfilled": "shipped"}


def get_order_status(printify_order_id: str) -> dict:
    """Poll Printify for order status + tracking (mocked in TEST_MODE).

    Normalized to the same shape gelato_api.get_gelato_order_status returns,
    so the fulfillment tracker can treat every vendor identically.
    """
    from quoteforge.config import PRINTIFY_API_KEY, PRINTIFY_SHOP_ID, TEST_MODE
    if TEST_MODE or not (PRINTIFY_API_KEY and PRINTIFY_SHOP_ID):
        return {"mock": True, "vendor": "printify", "status": "unknown",
                "tracking_number": "", "tracking_url": "", "carrier": ""}
    req = urllib.request.Request(
        f"https://api.printify.com/v1/shops/{PRINTIFY_SHOP_ID}"
        f"/orders/{printify_order_id}.json",
        headers={"Authorization": f"Bearer {PRINTIFY_API_KEY}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    raw = (data.get("status") or "unknown").lower()
    # Partially-fulfilled orders can carry tracking on a later shipment -
    # scan for the first one WITH a number (Gelato-adapter parity).
    shipments = data.get("shipments") or []
    shipment = next((s for s in shipments if s.get("number")),
                    shipments[0] if shipments else {})
    return {
        "vendor": "printify",
        "status": _STATUS_MAP.get(raw, raw),
        "tracking_number": shipment.get("number", ""),
        "tracking_url": shipment.get("url", ""),
        "carrier": shipment.get("carrier", ""),
        "raw": data,
    }


def verify_printify_auth() -> dict:
    """Live check that the Printify key + shop id are valid (no order created)."""
    from quoteforge.config import PRINTIFY_API_KEY, PRINTIFY_SHOP_ID
    if not (PRINTIFY_API_KEY and PRINTIFY_SHOP_ID):
        return {"ok": False,
                "detail": "PRINTIFY_API_KEY / PRINTIFY_SHOP_ID not set"}
    req = urllib.request.Request(
        "https://api.printify.com/v1/shops.json",
        headers={"Authorization": f"Bearer {PRINTIFY_API_KEY}"})
    try:
        # urlopen raises HTTPError on any non-2xx, so reaching here means OK.
        with urllib.request.urlopen(req, timeout=15):
            return {"ok": True, "detail": "authenticated (shops reachable)"}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"ok": False,
                    "detail": f"auth rejected (HTTP {exc.code}) - check key"}
        return {"ok": False, "detail": f"unexpected HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
