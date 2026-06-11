"""Fulfillment tracking sync - the missing order->delivery link.

For every in-production/shipped order: poll its vendor (Gelato, Printify, or
Printful — chosen by the order's `vendor` column) for tracking, update the order
to 'shipped' (and 'delivered' when the vendor reports it), and push the carrier
+ tracking number back to the Etsy buyer ONCE (createReceiptShipment). This is
what advances orders to delivery and lets the post-delivery review/delight loop
fire. Scheduled; TEST_MODE-safe (every vendor returns a mock, no real calls).

The order's `gelato_order_id` column holds the vendor order id for ALL vendors
(the pipeline stores the router's returned id there regardless of vendor).
"""
from __future__ import annotations


def _poll_vendor(order: dict, vendor_order_id: str) -> dict:
    """One status check against the order's vendor; updates tracking in the DB
    when it first appears (same contract as gelato_api.check_and_update_tracking)."""
    vendor = (order.get("vendor") or "gelato").lower()
    if vendor == "printify":
        from quoteforge.fulfillment.printify import get_order_status
    elif vendor == "printful":
        from quoteforge.fulfillment.printful import get_order_status
    else:
        from quoteforge.automation.gelato_api import check_and_update_tracking
        return check_and_update_tracking(order["order_id"], vendor_order_id)
    status = get_order_status(vendor_order_id)
    tn = status.get("tracking_number", "")
    if tn:
        from quoteforge.db.database import update_order
        update_order(order["order_id"], tracking_number=tn, status="shipped")
    return status


def sync_tracking(limit: int = 500) -> dict:
    from quoteforge.db.database import init_db, get_all_orders, update_order
    init_db()
    newly_shipped, delivered, pushed = [], [], []
    for o in get_all_orders(limit):
        gid = o.get("gelato_order_id")
        if not gid or o.get("status") in ("delivered", "cancelled", "refunded"):
            continue
        had_tracking = bool(o.get("tracking_number"))
        try:
            status = _poll_vendor(o, gid)  # may set shipped
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
            if not o.get("shipped_at"):
                from datetime import datetime as _dt
                update_order(o["order_id"], shipped_at=_dt.now().isoformat())

        if gstatus == "delivered":
            from datetime import datetime as _dt
            fields = {"status": "delivered"}
            if not o.get("delivered_at"):
                fields["delivered_at"] = _dt.now().isoformat()
            update_order(o["order_id"], **fields)
            delivered.append(o["order_id"])
    return {"checked": True, "newly_shipped": newly_shipped,
            "pushed_to_etsy": pushed, "delivered": delivered}


def format_tracking_text(r: dict) -> str:
    return ("Fulfillment tracking sync\n" + "-" * 34 + "\n"
            f"  Newly shipped : {len(r['newly_shipped'])}\n"
            f"  Pushed to Etsy: {len(r['pushed_to_etsy'])}\n"
            f"  Delivered     : {len(r['delivered'])}")
