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
