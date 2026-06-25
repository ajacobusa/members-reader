"""Route an order to the right vendor's fulfillment automatically.

Picks the adapter by the order's `vendor`:
  gelato            -> Gelato API (existing)
  printful          -> Printful API
  printify          -> Printify API
  digital/service/local/unknown -> 'manual' (flagged for you; nothing auto-sent)

API adapters are key-gated and TEST_MODE-safe, so this is a no-op until you add
the relevant vendor key - then non-Gelato products auto-route too.
"""
from __future__ import annotations

import threading

# Per-order routing locks: two concurrent duplicate webhooks each spawn a daemon
# thread that runs the pipeline and reaches route_order. Without serialization both
# can read vendor_order_id=None and BOTH submit to the supplier (duplicate print +
# charge). A per-order lock makes the critical section (dedup-check -> submit ->
# store) atomic within the process; the loser re-reads the now-stored vendor id and
# is blocked as a duplicate. Pure in-memory: no DB sentinel that a mid-submit crash
# could strand the order on.
_ROUTE_LOCKS: dict = {}
_ROUTE_LOCKS_GUARD = threading.Lock()


def _route_lock(order_id: str) -> threading.Lock:
    """The lock guarding routing for one order id (created on first use)."""
    with _ROUTE_LOCKS_GUARD:
        lk = _ROUTE_LOCKS.get(order_id)
        if lk is None:
            lk = _ROUTE_LOCKS[order_id] = threading.Lock()
        return lk


def route_order(order: dict, recipient: dict = None, artwork_url: str = "") -> dict:
    """Send the order to its vendor's API, serialized per order id so concurrent
    duplicate deliveries can't double-submit. Thin wrapper around the impl."""
    order_id = order.get("order_id") or order.get("etsy_order_id") or ""
    if not order_id:
        return _route_order_impl(order, recipient, artwork_url)
    with _route_lock(order_id):
        return _route_order_impl(order, recipient, artwork_url)


def _route_order_impl(order: dict, recipient: dict = None, artwork_url: str = "") -> dict:
    """Send the order to its vendor's API (gelato/printful/printify)."""
    vendor = (order.get("vendor") or "gelato").lower()
    order_id = order.get("order_id") or order.get("etsy_order_id") or ""
    recipient = recipient or order.get("recipient_address") or {}

    # Idempotency: never double-submit. If this order already carries a supplier
    # order id, it is already routed - return that instead of creating a duplicate.
    if order_id:
        from quoteforge.db.database import get_order
        try:
            existing = get_order(order_id)
        except Exception as exc:  # noqa: BLE001
            # If the dedup lookup fails we must NOT proceed - routing anyway could
            # double-submit (double supplier charge). Fail safe and surface it.
            import logging
            logging.getLogger(__name__).warning(
                "route_order dedup lookup failed for %s: %s", order_id, exc)
            return {"status": "error", "vendor": vendor, "id": "",
                    "detail": f"dedup lookup failed; not routing to avoid a "
                              f"duplicate submission: {exc}"}
        if existing and existing.get("vendor_order_id"):
            return {"status": "duplicate", "vendor": vendor,
                    "id": existing["vendor_order_id"],
                    "detail": "order already routed - duplicate submission blocked"}

    if vendor == "gelato":
        from quoteforge.config import TEST_MODE
        product_uid = order.get("gelato_product_uid") or order.get("product_uid")
        # Defence in depth: a GEL-* seed placeholder must NEVER be submitted to
        # production. Route to manual so the owner maps the real Gelato UID first
        # (protects both apparel and any print SKU left on a placeholder).
        if product_uid and str(product_uid).upper().startswith("GEL-"):
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "placeholder product UID - map the real Gelato UID "
                              "in GELATO_UID_MAP before fulfilment"}
        # A 12-month calendar is a multi-image product: production needs all 12 month
        # photos (get_design_for_order holds the URLs), which the single-file
        # submission path cannot carry yet. NEVER auto-submit a calendar as cover-only
        # (silent under-delivery / chargeback); hold for manual production instead.
        if str(order.get("product_type", "")).lower() == "calendar":
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "12-month calendar needs multi-image production - "
                              "manual fulfilment (all 12 month photos)"}
        if not (product_uid and recipient and artwork_url):
            return {"status": "manual", "vendor": "gelato",
                    "detail": "missing product/address/artwork - manual upload",
                    "id": ""}
        # Normalise + validate the ship-to BEFORE creating the order, so a bad
        # address is fixed/flagged here instead of returning-to-sender later.
        from quoteforge.fulfillment.gelato_returns import normalize_recipient
        norm = normalize_recipient(recipient)
        if not norm["valid"]:
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "address incomplete (" + ", ".join(norm["issues"])
                    + ") - verify to prevent return-to-sender"}
        recipient = norm["recipient"]
        # Persist the validated ship-to so a later replacement reprint can reuse
        # it without re-collecting the address.
        try:
            import json
            from quoteforge.db.database import update_order, get_order
            if get_order(order_id):
                update_order(order_id, ship_to=json.dumps(recipient))
        except Exception:  # noqa: BLE001 - persistence is best-effort, never block routing
            pass
        try:
            from quoteforge.automation.gelato_api import create_gelato_order
            resp = create_gelato_order(order_id=order_id, recipient=recipient,
                                       artwork_url=artwork_url, product_uid=product_uid)
            vid = resp.get("id", "")
            # Self-store the supplier order id on success so the idempotency guard
            # is robust even if the caller forgets to persist it.
            try:
                from quoteforge.db.database import update_order, get_order
                if vid and get_order(order_id):
                    update_order(order_id, vendor_order_id=vid)
            except Exception:  # noqa: BLE001
                pass
            return {"status": "submitted", "vendor": "gelato",
                    "id": vid, "raw": resp}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "vendor": "gelato", "detail": str(exc), "id": ""}

    if vendor == "printful":
        from quoteforge.fulfillment import printful
        return printful.create_order(order_id, recipient, artwork_url,
                                     order.get("variant_id"))
    if vendor == "printify":
        from quoteforge.fulfillment import printify
        return printify.create_order(order_id, recipient, artwork_url,
                                     line_items=order.get("line_items", []))
    if vendor == "digital":
        return {"status": "fulfilled", "vendor": "digital",
                "detail": "digital item - delivered electronically", "id": ""}
    return {"status": "manual", "vendor": vendor,
            "detail": f"{vendor}: fulfill by hand", "id": ""}
