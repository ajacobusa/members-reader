"""Fulfillment tracking sync - the missing order->delivery link.

For every in-production/shipped order: poll Gelato for tracking, update the order
to 'shipped' (and 'delivered' when Gelato reports it), and push the carrier +
tracking number back to the Etsy buyer ONCE (createReceiptShipment). This is
what advances orders to delivery and lets the post-delivery review/delight loop
fire. Scheduled; TEST_MODE-safe (Gelato returns a mock, no real calls).
"""
from __future__ import annotations


def sync_tracking(limit: int = 500) -> dict:
    from quoteforge.db.database import init_db, get_all_orders, update_order
    from quoteforge.automation.gelato_api import check_and_update_tracking
    init_db()
    newly_shipped, delivered, pushed = [], [], []
    for o in get_all_orders(limit):
        gid = o.get("gelato_order_id")
        if not gid or o.get("status") in ("delivered", "cancelled", "refunded"):
            continue
        had_tracking = bool(o.get("tracking_number"))
        try:
            status = check_and_update_tracking(o["order_id"], gid)  # may set shipped
        except Exception:  # noqa: BLE001
            continue
        tn = status.get("tracking_number", "")
        gstatus = (status.get("status") or "").lower()

        # Push tracking to the Etsy buyer once (only when it first appears).
        if tn and not had_tracking and o.get("etsy_order_id"):
            try:
                from quoteforge.automation.etsy_api import create_receipt_shipment
                create_receipt_shipment(
                    o["etsy_order_id"], tn,
                    carrier_name=status.get("carrier", "other"))
                pushed.append(o["order_id"])
            except Exception:  # noqa: BLE001
                pass
            newly_shipped.append(o["order_id"])

        if gstatus == "delivered":
            update_order(o["order_id"], status="delivered")
            delivered.append(o["order_id"])
    return {"checked": True, "newly_shipped": newly_shipped,
            "pushed_to_etsy": pushed, "delivered": delivered}


def format_tracking_text(r: dict) -> str:
    return ("Fulfillment tracking sync\n" + "-" * 34 + "\n"
            f"  Newly shipped : {len(r['newly_shipped'])}\n"
            f"  Pushed to Etsy: {len(r['pushed_to_etsy'])}\n"
            f"  Delivered     : {len(r['delivered'])}")
