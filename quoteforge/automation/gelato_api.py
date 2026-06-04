"""Gelato API client — programmatic print order creation.

Replaces the manual Gelato dashboard upload workflow.
API docs: developers.gelato.com
"""
import os
import time
import requests
from quoteforge.config import TEST_MODE

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
    # TEST_MODE / no key → return a mock order without spending money or printing
    if TEST_MODE or not GELATO_API_KEY:
        return {
            "id": f"TEST-GELATO-{order_id}",
            "gelato_order_id": f"TEST-GELATO-{order_id}",
            "tracking_number": "TEST-TRACKING-123",
            "fulfillmentStatus": "test_mode",
            "test_mode": True,
        }

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
    """Poll order status until shipped or max_polls reached.

    WARNING: This BLOCKS the calling thread for up to max_polls * interval_secs
    (default 48 hours). NEVER call this from a web request or the GUI thread.
    Run it only from a dedicated background worker / scheduled job, or instead
    call get_gelato_order_status() once per scheduled tick (recommended).
    """
    for _ in range(max_polls):
        status = get_gelato_order_status(gelato_order_id)
        if status["status"] in ("shipped", "delivered"):
            return status
        time.sleep(interval_secs)
    return get_gelato_order_status(gelato_order_id)


def check_and_update_tracking(order_id: str, gelato_order_id: str) -> dict:
    """Non-blocking single status check — meant to be run on a schedule.

    Polls Gelato once, updates the order's tracking number in the DB if shipped.
    Returns the status dict. This is the recommended alternative to the blocking
    poll_until_shipped for production (call it from /backup-style scheduled hits).
    """
    status = get_gelato_order_status(gelato_order_id)
    tn = status.get("tracking_number", "")
    if tn:
        from quoteforge.db.database import update_order
        update_order(order_id, tracking_number=tn, status="shipped")
    return status


def verify_gelato_auth() -> dict:
    """Live check that GELATO_API_KEY is valid (hits the catalog API).

    Returns {"ok": bool, "detail": str}. Does NOT create any order.
    """
    if not GELATO_API_KEY:
        return {"ok": False, "detail": "GELATO_API_KEY not set"}
    try:
        resp = requests.get(
            "https://product.gelatoapis.com/v3/catalogs",
            headers={"X-API-KEY": GELATO_API_KEY},
            timeout=15,
        )
        if resp.status_code == 200:
            return {"ok": True, "detail": "authenticated (catalog reachable)"}
        if resp.status_code in (401, 403):
            return {"ok": False, "detail": f"auth rejected (HTTP {resp.status_code}) — check key"}
        return {"ok": False, "detail": f"unexpected HTTP {resp.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


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
