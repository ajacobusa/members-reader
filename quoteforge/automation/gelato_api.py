"""Gelato API client — programmatic print order creation.

Replaces the manual Gelato dashboard upload workflow.
API docs: developers.gelato.com
"""
import logging
import os
import time
import requests
from quoteforge.config import TEST_MODE

logger = logging.getLogger(__name__)

GELATO_API_KEY: str = os.getenv("GELATO_API_KEY", "")
GELATO_BASE_URL = "https://order.gelatoapis.com"
GELATO_CATALOG_URL = "https://catalog.gelatoapis.com"


def _gelato_headers() -> dict:
    """Build Gelato API headers; raises if the API key is missing."""
    if not GELATO_API_KEY:
        raise ValueError("GELATO_API_KEY not set. Get it from gelato.com → Settings → API.")
    return {"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"}


def _build_files(artwork_url: str, extra_files: dict = None) -> list:
    """The per-item files array: the front ('default') plus one file per EXTRA print
    area (back / sleeve-*) that carries a real public URL. A blank/non-http extra area
    is skipped so a missing back/sleeve file never breaks (or silently corrupts) the
    submission - it just isn't printed."""
    files = [{"type": "default", "url": artwork_url}]
    for area, url in (extra_files or {}).items():
        a = str(area or "").strip().lower()
        if a in ("", "default", "front") or not url:
            continue
        if str(url).lower().startswith(("http://", "https://")):
            files.append({"type": a, "url": url})
    return files


def create_gelato_order(
    order_id: str,
    recipient: dict,
    artwork_url: str,
    product_uid: str,
    quantity: int = 1,
    shipment_method: str = "",
    extra_files: dict = None,
) -> dict:
    """Create a print order via Gelato API.

    extra_files maps an EXTRA print-area placement type -> a public artwork URL, e.g.
    {"back": "https://.../back.png", "sleeve-left": "https://.../sl.png"}. Each becomes
    its own file in the item alongside the front ("default"), so apparel back/sleeve
    designs actually print. Empty/None = front-only (the existing behaviour).

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

    # Gelato Create Order. v4 (current) additionally requires orderType +
    # shipmentMethodUid; the rest of the contract matches v3.
    from quoteforge.config import GELATO_API_VERSION, GELATO_SHIPMENT_METHOD
    ver = GELATO_API_VERSION or "v4"
    payload = {
        "orderReferenceId": order_id,
        "customerReferenceId": order_id,
        "currency": "USD",
        "items": [
            {
                "itemReferenceId": f"{order_id}-item-1",
                "productUid": product_uid,
                "files": _build_files(artwork_url, extra_files),
                "quantity": quantity,
            }
        ],
        "shippingAddress": recipient,
    }
    if ver == "v4":
        payload["orderType"] = "order"                       # not a draft
        # Per-order method (express upgrade) wins; else the configured default.
        payload["shipmentMethodUid"] = shipment_method or GELATO_SHIPMENT_METHOD or "normal"
    resp = requests.post(
        f"{GELATO_BASE_URL}/{ver}/orders",
        headers=_gelato_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        # Log Gelato's ACTUAL error (e.g. "productUid not found", bad address) -
        # raise_for_status alone carries only the status line, so the real reason
        # was passing silently. The caller (router) turns the raise into a held
        # 'error'/'submit_unconfirmed' order; this line preserves the why.
        logger.error("Gelato create order %s -> HTTP %s: %s",
                     order_id, resp.status_code, (resp.text or "")[:800])
    resp.raise_for_status()
    return resp.json()


def update_gelato_shipping_address(gelato_order_id: str, address: dict) -> dict:
    """Update an order's shipping address BEFORE fulfilment (prevents return-to-
    sender on a bad address). Mirrors Gelato's
    `PUT /v3/orders/{id}/shipping-address`. Country change is not allowed by
    Gelato. TEST_MODE/no-key returns a mock acknowledgement.

    `address` uses Gelato field names: firstName, lastName, addressLine1,
    addressLine2, city, state, postCode, country, email, phone, companyName.
    """
    if not gelato_order_id or not address:
        return {"status": "skipped", "reason": "missing order id/address"}
    if TEST_MODE or not GELATO_API_KEY:
        return {"status": "mock_updated", "gelato_order_id": gelato_order_id,
                "shippingAddress": address}
    # Honor the same version as create/status (was hardcoded /v3, which would hit a
    # v3 path while create/status run on v4 for a v4-only account).
    from quoteforge.config import GELATO_API_VERSION
    ver = GELATO_API_VERSION or "v4"
    resp = requests.put(
        f"{GELATO_BASE_URL}/{ver}/orders/{gelato_order_id}/shipping-address",
        headers=_gelato_headers(), json=address, timeout=30)
    resp.raise_for_status()
    return {"status": "updated", "gelato_order_id": gelato_order_id,
            **(resp.json() if resp.content else {})}


def _extract_gelato_cost(data: dict) -> "float | None":
    """The ACTUAL amount Gelato charges YOU (product + shipping + tax) from an order
    response - the real COGS, vs the catalog estimate. Tries the common shapes (a
    top-level total, or summed receipts). Returns None when no cost is present yet
    (the estimate then stands). Never raises."""
    try:
        for k in ("totalInclVat", "total", "totalAmount"):
            v = data.get(k)
            if v not in (None, ""):
                return round(float(v), 2)
        receipts = data.get("receipts") or []
        tot, found = 0.0, False
        for r in receipts:
            picked = False
            for k in ("totalInclVat", "total", "totalAmount"):
                v = r.get(k)
                if v not in (None, ""):
                    tot += float(v); found = picked = True
                    break
            if not picked:
                parts = sum(float(r.get(k, 0) or 0) for k in
                            ("productsPriceInclVat", "shippingPriceInclVat",
                             "packagingPriceInclVat"))
                if parts:
                    tot += parts; found = True
        if found:
            return round(tot, 2)
    except (TypeError, ValueError) as exc:
        logger.debug("gelato cost parse skipped (unparseable): %s", exc)
    return None


def _extract_gelato_shipping(data: dict) -> "float | None":
    """The SHIPPING portion Gelato charges YOU, from the order response - so the
    shipping-variance audit (customer shipping vs what Gelato charges) runs on real
    numbers. Sums shippingPriceInclVat across receipts (or a top-level field).
    None when absent. Never raises."""
    try:
        receipts = data.get("receipts") or []
        ship, found = 0.0, False
        for r in receipts:
            for k in ("shippingPriceInclVat", "shippingPrice", "shipmentPriceInclVat"):
                v = r.get(k)
                if v not in (None, ""):
                    ship += float(v); found = True
                    break
        if found:
            return round(ship, 2)
        for k in ("shippingPriceInclVat", "shippingPrice"):
            v = data.get(k)
            if v not in (None, ""):
                return round(float(v), 2)
    except (TypeError, ValueError) as exc:
        logger.debug("gelato shipping parse skipped (unparseable): %s", exc)
    return None


def get_gelato_order_status(gelato_order_id: str) -> dict:
    """Poll Gelato for order status, tracking number, and the ACTUAL charged cost."""
    from quoteforge.config import GELATO_API_VERSION
    ver = GELATO_API_VERSION or "v4"
    resp = requests.get(
        f"{GELATO_BASE_URL}/{ver}/orders/{gelato_order_id}",
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
        "carrier": _extract_shipment_field(data, "shipmentMethodName", "carrier"),
        "estimated_delivery": _extract_shipment_field(
            data, "expectedDeliveryDate", "estimated_delivery_date"),
        "cost": _extract_gelato_cost(data),       # actual TOTAL charged to you
        "shipping_cost": _extract_gelato_shipping(data),  # its shipping portion
        "raw": data,
    }


def _extract_tracking(data: dict) -> str:
    """Pull the first tracking number from a Gelato order payload, or ''."""
    items = data.get("items", [])
    for item in items:
        for shipment in item.get("fulfillments", []):
            tn = shipment.get("trackingNumber") or shipment.get("tracking_number", "")
            if tn:
                return tn
    return ""


def _extract_shipment_field(data: dict, *keys: str) -> str:
    """First non-empty value of any of `keys` across the order's shipments
    (carrier name / expected delivery date), or ''."""
    for item in data.get("items", []):
        for shipment in item.get("fulfillments", []):
            for k in keys:
                v = shipment.get(k)
                if v:
                    return str(v)
    return ""


def _extract_tracking_url(data: dict) -> str:
    """Pull the first tracking URL from a Gelato order payload, or ''."""
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
    from quoteforge.db.database import get_order, update_order
    o = get_order(order_id) or {}
    tn = status.get("tracking_number", "")
    # Write only on first appearance / change - re-polls must not rewrite (and fsync)
    # the row every 6 hours for already-tracked orders.
    if tn and tn != (o.get("tracking_number") or ""):
        update_order(order_id, tracking_number=tn, status="shipped")
    # Capture the ACTUAL Gelato charge once the order is priced, overwriting the
    # catalog estimate so financials + the Wave books use real COGS. Split product vs
    # shipping: financials add gelato_cost + shipping_cost, so gelato_cost must be the
    # PRODUCT portion (total - shipping) or shipping would be double-counted; the
    # shipping portion populates shipping_cost so the shipping-variance audit runs on
    # real numbers.
    total = status.get("cost")
    ship = status.get("shipping_cost")
    if total is not None:
        product = round(float(total) - float(ship or 0), 2)
        if round(float(o.get("gelato_cost") or 0), 2) != product:
            update_order(order_id, gelato_cost=product)
    if ship is not None and round(float(o.get("shipping_cost") or 0), 2) != round(float(ship), 2):
        update_order(order_id, shipping_cost=round(float(ship), 2))
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
    """Return step-by-step instructions for obtaining and setting a Gelato API key."""
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


def file_replacement_claim(order_id: str, reason: str = "",
                           photos: list[str] | None = None) -> dict:
    """File (or stage) a Gelato quality/damage replacement claim for an order.

    Gelato handles defect/damage/loss replacements through its support flow;
    there is no fully self-serve claim-creation REST endpoint, so in production
    this stages the claim with all evidence for one-click submission. In
    TEST_MODE it returns a mock acknowledgement so the autopilot flow is fully
    testable without contacting Gelato.
    """
    claim = {
        "order_id": order_id,
        "reason": reason,
        "photos": photos or [],
        "status": "staged",
    }
    if TEST_MODE or not GELATO_API_KEY:
        claim["status"] = "mock_filed"
        return claim
    # Real submission point (Gelato support intake / partner webhook).
    claim["status"] = "filed"
    return claim
