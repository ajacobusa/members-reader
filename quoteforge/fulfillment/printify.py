"""Printify fulfillment adapter (stdlib HTTP).

Submits a Printify order when PRINTIFY_API_KEY + PRINTIFY_SHOP_ID are set;
otherwise returns a 'manual' result. Never raises.
"""
from __future__ import annotations

import json
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
