"""Gelato live-seam operations - the defensive, gated bridge to a REAL Gelato/Etsy account.

Components 2-4 of zero-owner-iteration, each a no-op until genuinely live and each
DEFENSIVE about the unverified provider shapes (never raises; returns a blocked/empty
result on anything unexpected - the shape is confirmed + logged on the first live call):

  2. create_first_live_product  - create the first store product from a Gelato template and
     capture the raw create response into gelato_live_probe (idempotent: one probe).
  3. sync_live_image_shapes     - pull the live Gelato product + Etsy listing images back and
     record the detected image shape (Gate 2 confirmed).
  4. submit_calibration_test_order - place ONE real physical apparel test order to drive the
     vision-QA calibration. MONEY-OUT, so it is OFF by default and hard-capped: explicit
     CALIBRATION_TEST_ORDER_ENABLED consent, one open test order per productUid (idempotent),
     cost <= CALIBRATION_TEST_ORDER_MAX_SPEND, and it ALWAYS routes through the same
     idempotent router as a customer order (no back-door create).

Nothing here fabricates a productUid or flips a safety flag. In TEST_MODE / without a key
every function is a safe no-op.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_PRODUCT_API = "https://product.gelatoapis.com/v3"


def _live() -> bool:
    """True only when genuinely live (TEST_MODE off + a Gelato key present)."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return (not TEST_MODE) and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


# ── Component 2: create the first live product from a template ───

def _gelato_create_from_template(store_id: str, template_id: str, title: str,
                                 description: str) -> dict:
    """DEFENSIVE live seam: POST products:create-from-template to the Gelato ecommerce
    store. Never raises; returns {} on anything unexpected. The exact request/response
    shape is the one thing to confirm against a live Gelato account (it is captured raw
    into the probe so the shape is visible on the first real call)."""
    try:
        import requests
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        from quoteforge.config import GELATO_ECOMMERCE_URL
        resp = requests.post(
            f"{GELATO_ECOMMERCE_URL}/v1/stores/{store_id}/products:create-from-template",
            headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
            json={"templateId": template_id, "title": title, "description": description},
            timeout=30)
        if resp.status_code not in (200, 201):
            logger.warning("create-from-template -> %s", resp.status_code)
            return {}
        return resp.json() if isinstance(resp.json(), dict) else {}
    except Exception as exc:  # noqa: BLE001 - unverified provider shape: never crash
        logger.warning("create-from-template failed (defensive): %s", exc)
        return {}


def create_first_live_product(template_id: str, title: str, *, description: str = "",
                              qf_product_id: str = "", sku: str = "",
                              creator=None) -> dict:
    """Create the first live store product from a Gelato template and record a probe.
    Idempotent: if a probe already exists, returns it without creating again. No-op (returns
    {skipped}) in TEST_MODE / without a store id. `creator` is injectable for testing."""
    from quoteforge.automation.gelato_readiness import latest_probe, record_live_probe
    existing = latest_probe()
    if existing:
        return {"skipped": "probe already exists", "probe_id": existing.get("id"),
                "status": existing.get("status")}
    if creator is None and not _live():
        return {"skipped": "not live (TEST_MODE / no key)"}
    from quoteforge.config import GELATO_STORE_ID
    if not GELATO_STORE_ID:
        return {"skipped": "GELATO_STORE_ID not set"}
    if not template_id:
        return {"skipped": "no templateId (create the template in the Gelato dashboard)"}
    make = creator or (lambda: _gelato_create_from_template(
        GELATO_STORE_ID, template_id, title, description))
    raw = make() or {}
    gelato_product_id = ""
    for k in ("id", "productId", "storeProductId", "productUid"):
        if isinstance(raw.get(k), str) and raw[k]:
            gelato_product_id = raw[k]
            break
    pid = record_live_probe(qf_product_id or title, sku,
                            gelato_store_id=GELATO_STORE_ID,
                            gelato_template_id=template_id,
                            gelato_product_id=gelato_product_id,
                            raw_create_response=raw,
                            status="created" if gelato_product_id else "create_failed")
    return {"probe_id": pid, "gelato_product_id": gelato_product_id,
            "created": bool(gelato_product_id)}


# ── Component 3: sync the live image shape back ──────────────────

def sync_live_image_shapes(*, gelato_fetch=None, etsy_fetch=None) -> dict:
    """Pull the live Gelato product + Etsy listing images for the latest probe and record
    the detected image shape (Gate 2 confirmed). No-op if no probe / not live. Fetchers are
    injectable for testing. Never raises."""
    from quoteforge.automation.gelato_readiness import latest_probe, confirm_image_shape
    probe = latest_probe()
    if not probe:
        return {"skipped": "no probe yet - create the first product first"}
    if gelato_fetch is None and etsy_fetch is None and not _live():
        return {"skipped": "not live (TEST_MODE / no key)"}
    gp = {}
    ei = {}
    try:
        if gelato_fetch is not None:
            gp = gelato_fetch(probe.get("gelato_product_id")) or {}
        else:
            from quoteforge.automation import ecommerce_images as ecom
            from quoteforge.config import GELATO_STORE_ID
            gp = ecom._product_detail(GELATO_STORE_ID, probe.get("gelato_product_id") or "") or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("gelato product fetch failed (defensive): %s", exc)
    try:
        if etsy_fetch is not None:
            ei = etsy_fetch(probe) or {}
        else:
            from quoteforge.automation import etsy_api
            _lid = (gp.get("externalId") or gp.get("etsyListingId") or "")
            ei = etsy_api.official_listing_images(_lid) if _lid else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("etsy image fetch failed (defensive): %s", exc)
    row = confirm_image_shape(probe["id"], raw_gelato_product_response=gp,
                              raw_etsy_image_response=ei)
    return {"probe_id": probe["id"], "detected_image_shape": row.get("detected_image_shape"),
            "status": row.get("status")}


# ── Component 4: spend-capped physical test-print order ──────────

def _test_order_placed_for(product_uid: str) -> bool:
    """True if a calibration test order (or approval) already exists for this productUid -
    the idempotency guard so a re-run never double-orders."""
    from quoteforge.db.database import _conn
    with _conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM apparel_print_calibration WHERE product_uid=? "
            "AND status IN ('test_ordered','approved')", (product_uid,)).fetchone()["n"]
    return int(n) > 0


def submit_calibration_test_order(product_uid: str, recipient: dict, artwork_url: str, *,
                                  est_cost: float = 0.0, router=None) -> dict:
    """Place ONE real physical apparel test order to drive vision-QA calibration. Heavily
    gated (money-out): returns a {blocked: reason} unless every rail holds -
    CALIBRATION_TEST_ORDER_ENABLED consent, genuinely live, a real (non-GEL-*) UID, a known
    cost within CALIBRATION_TEST_ORDER_MAX_SPEND, and no existing test order for this UID.
    ALWAYS routes through the idempotent router (never a back-door create). Records a
    'test_ordered' calibration row on success. `router` is injectable for testing."""
    from quoteforge.config import (CALIBRATION_TEST_ORDER_ENABLED,
                                    CALIBRATION_TEST_ORDER_MAX_SPEND, TEST_MODE)
    product_uid = (product_uid or "").strip()
    if not CALIBRATION_TEST_ORDER_ENABLED:
        return {"blocked": "CALIBRATION_TEST_ORDER_ENABLED is off (one-time owner consent)"}
    if router is None and (TEST_MODE or not _live()):
        return {"blocked": "not live (TEST_MODE / no key)"}
    if not product_uid or product_uid.upper().startswith("GEL-"):
        return {"blocked": "no real productUid (placeholder/empty rejected)"}
    if not (recipient and artwork_url):
        return {"blocked": "missing recipient/artwork for the test order"}
    if est_cost <= 0 or est_cost > float(CALIBRATION_TEST_ORDER_MAX_SPEND):
        return {"blocked": f"est_cost {est_cost} outside cap "
                           f"(0, {CALIBRATION_TEST_ORDER_MAX_SPEND}]"}
    if _test_order_placed_for(product_uid):
        return {"blocked": "a test order already exists for this productUid (idempotent)"}

    order = {"order_id": f"calib-{product_uid}", "gelato_product_uid": product_uid,
             "vendor": "gelato", "product_type": "apparel", "faithful_artwork": True,
             "calibration_test": True}
    route = router or _route
    result = route(order, recipient, artwork_url) or {}
    if result.get("status") in ("submitted", "ok", "success", "created"):
        from quoteforge.db.database import _conn
        with _conn() as conn:
            conn.execute(
                "INSERT INTO apparel_print_calibration (product_family, product_uid, status, "
                "approver, notes, test_order_ref, created_at) VALUES "
                "('apparel', ?, 'test_ordered', 'auto', ?, ?, datetime('now'))",
                (product_uid, f"est_cost={est_cost}", str(result.get("id") or "")))
        return {"ordered": True, "vendor_id": result.get("id"), "route": result}
    return {"ordered": False, "route": result}


def _route(order: dict, recipient: dict, artwork_url: str) -> dict:
    """Default router hop for the test order - the SAME idempotent route_order a customer
    order uses (so a test order can never double-submit or bypass the safety gates)."""
    from quoteforge.fulfillment.router import route_order
    return route_order(order, recipient=recipient, artwork_url=artwork_url)


def status() -> dict:
    """A quick read of live-ops readiness for the daily report / CLI."""
    from quoteforge.automation.gelato_readiness import latest_probe
    from quoteforge.config import (CALIBRATION_TEST_ORDER_ENABLED, GELATO_STORE_ID)
    p = latest_probe()
    return {"live": _live(), "store_id_set": bool(GELATO_STORE_ID),
            "probe": {"id": p["id"], "status": p["status"]} if p else None,
            "test_order_enabled": bool(CALIBRATION_TEST_ORDER_ENABLED)}
