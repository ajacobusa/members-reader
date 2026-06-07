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
    vendor = (order.get("vendor") or "gelato").lower()
    order_id = order.get("order_id") or order.get("etsy_order_id") or ""
    recipient = recipient or order.get("recipient_address") or {}

    if vendor == "gelato":
        from quoteforge.config import TEST_MODE
        product_uid = order.get("gelato_product_uid") or order.get("product_uid")
        if not (product_uid and recipient and artwork_url):
            return {"status": "manual", "vendor": "gelato",
                    "detail": "missing product/address/artwork - manual upload",
                    "id": ""}
        try:
            from quoteforge.automation.gelato_api import create_gelato_order
            resp = create_gelato_order(order_id=order_id, recipient=recipient,
                                       artwork_url=artwork_url, product_uid=product_uid)
            return {"status": "submitted", "vendor": "gelato",
                    "id": resp.get("id", ""), "raw": resp}
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
