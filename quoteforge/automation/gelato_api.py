"""Gelato API client — programmatic print order creation.

Replaces the manual Gelato dashboard upload workflow.
API docs: developers.gelato.com
"""
import time
import requests
from quoteforge.config import BANNERBEAR_API_KEY  # reuse existing config pattern

import os
GELATO_API_KEY: str = os.getenv("GELATO_API_KEY", "")
GELATO_BASE_URL = "https://order.gelatoapis.com"
GELATO_CATALOG_URL = "https://catalog.gelatoapis.com"


def _gelato_headers() -> dict:
    if not GELATO_API_KEY:
        raise ValueError("GELATO_API_KEY not set. Get it from gelato.com → Settings → API.")
    return {"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"}


def create_gelato_order(
    order_id: str,
    recipient: dict,
    artwork_url: str,
    product_uid: str,
    quantity: int = 1,
) -> dict:
    """Create a print order via Gelato API.

    recipient = {
        "name": "Emma Smith",
        "address": "123 Main St",
        "city": "Atlanta",
        "state": "GA",
        "postCode": "30301",
        "country": "US",
        "email": "customer@email.com",
    }
    product_uid = Gelato's product UID (e.g. "framed-poster_pf_14x11_pl_4-4_cl_4-0_ct_framed-poster_cp_1_cr_pr_0_ver_1")
    """
    payload = {
        "orderReferenceId": order_id,
        "customerReferenceId": order_id,
        "currency": "USD",
        "items": [
            {
                "itemReferenceId": f"{order_id}-item-1",
                "productUid": product_uid,
                "files": [{"type": "default", "url": artwork_url}],
                "quantity": quantity,
            }
        ],
        "shippingAddress": recipient,
    }
    resp = requests.post(
        f"{GELATO_BASE_URL}/v3/orders",
        headers=_gelato_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_gelato_order_status(gelato_order_id: str) -> dict:
    """Poll Gelato for order status and tracking number."""
    resp = requests.get(
        f"{GELATO_BASE_URL}/v3/orders/{gelato_order_id}",
        headers=_gelato_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "gelato_order_id": gelato_order_id,
        "status": data.get("fulfillmentStatus", "unknown"),
        "tracking_number": _extract_tracking(data),
        "tracking_url": _extract_tracking_url(data),
        "raw": data,
    }


def _extract_tracking(data: dict) -> str:
    items = data.get("items", [])
    for item in items:
        for shipment in item.get("fulfillments", []):
            tn = shipment.get("trackingNumber") or shipment.get("tracking_number", "")
            if tn:
                return tn
    return ""


def _extract_tracking_url(data: dict) -> str:
    items = data.get("items", [])
    for item in items:
        for shipment in item.get("fulfillments", []):
            url = shipment.get("trackingUrl") or shipment.get("tracking_url", "")
            if url:
                return url
    return ""


def poll_until_shipped(gelato_order_id: str, max_polls: int = 48, interval_secs: int = 3600) -> dict:
    """Poll order status hourly until shipped or max polls reached."""
    for _ in range(max_polls):
        status = get_gelato_order_status(gelato_order_id)
        if status["status"] in ("shipped", "delivered"):
            return status
        time.sleep(interval_secs)
    return get_gelato_order_status(gelato_order_id)


def get_gelato_api_setup() -> str:
    return """
GELATO API SETUP
================
1. Log into gelato.com
2. Go to: Settings → Developers → API Keys
3. Create a new API key
4. Set in config.py or .env:
   GELATO_API_KEY = "your_gelato_api_key"

Key endpoints used:
  POST /v3/orders        → create print order
  GET  /v3/orders/{id}   → get status + tracking

Product UIDs: find in Gelato catalog API or dashboard product details.
"""
