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


def route_order(order: dict, recipient: dict = None, artwork_url: str = "") -> dict:
    """Send the order to its vendor's API (gelato/printful/printify)."""
    vendor = (order.get("vendor") or "gelato").lower()
    order_id = order.get("order_id") or order.get("etsy_order_id") or ""
    recipient = recipient or order.get("recipient_address") or {}

    # Idempotency: never double-submit. If this order is already routed (a vendor
    # order id is on record), return that instead of creating a duplicate.
    if order_id:
        try:
            from quoteforge.db.database import get_order
            existing = get_order(order_id)
            if existing and existing.get("vendor_order_id"):
                return {"status": "duplicate", "vendor": vendor,
                        "id": existing["vendor_order_id"],
                        "detail": "order already routed - duplicate submission blocked"}
        except Exception:  # noqa: BLE001 - never let the guard block a real route
            pass

    if vendor == "gelato":
        from quoteforge.config import TEST_MODE
        product_uid = order.get("gelato_product_uid") or order.get("product_uid")
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
            # Store the supplier order id on success so the idempotency guard and
            # tracking sync are self-contained (caller no longer has to).
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
