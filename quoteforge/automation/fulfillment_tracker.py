"""Fulfillment tracking sync - the missing order->delivery link.

For every in-production/shipped order: poll its vendor (Gelato, Printify, or
Printful — chosen by the order's `vendor` column) for tracking, update the order
to 'shipped', and push the carrier + tracking number back to the Etsy buyer ONCE
(createReceiptShipment). Gelato reports delivery, so its orders advance to
'delivered' from the API; Printify/Printful order APIs never report delivery,
so their shipped orders are assumed delivered ASSUME_DELIVERED_DAYS after
shipping (and are not re-polled once tracking is known - the API has nothing
new to say). This is what advances orders to delivery and lets the
post-delivery review/delight loop fire. Scheduled; TEST_MODE-safe.

The order's `gelato_order_id` column holds the vendor order id for ALL vendors
(the pipeline stores the router's returned id there regardless of vendor).
"""
from __future__ import annotations

# Printify/Printful don't report delivery; assume it this many days after the
# ship date (domestic parcels arrive in 2-8 days; 14 is a safe outer bound).
ASSUME_DELIVERED_DAYS = 14

# Vendors whose order API stops giving new information once tracking exists.
_NO_DELIVERY_SIGNAL = ("printify", "printful")


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
    if tn and tn != (order.get("tracking_number") or ""):
        from quoteforge.db.database import update_order
        update_order(order["order_id"], tracking_number=tn, status="shipped")
    return status


def _assume_delivered(order: dict, delivered: list) -> None:
    """Advance a tracked Printify/Printful order to 'delivered' once it has
    been shipped for ASSUME_DELIVERED_DAYS (their APIs never report delivery)."""
    from datetime import datetime as _dt
    shipped_at = order.get("shipped_at") or ""
    try:
        age_days = (_dt.now() - _dt.fromisoformat(shipped_at)).days
    except ValueError:
        return                      # no/invalid ship date: wait for next run
    if age_days >= ASSUME_DELIVERED_DAYS:
        from quoteforge.db.database import update_order
        update_order(order["order_id"], status="delivered",
                     delivered_at=_dt.now().isoformat())
        delivered.append(order["order_id"])


def sync_tracking(limit: int = 500) -> dict:
    """Poll vendors for all open orders, advance statuses, and push new
    tracking numbers to the Etsy buyer once."""
    from quoteforge.db.database import init_db, get_all_orders, update_order
    init_db()
    newly_shipped, delivered, pushed = [], [], []
    for o in get_all_orders(limit):
        gid = o.get("gelato_order_id")
        if not gid or o.get("status") in ("delivered", "cancelled", "refunded"):
            continue
        had_tracking = bool(o.get("tracking_number"))
        vendor = (o.get("vendor") or "gelato").lower()

        # Printify/Printful with known tracking: nothing new to poll - just
        # age the order toward assumed delivery.
        if vendor in _NO_DELIVERY_SIGNAL and had_tracking:
            _assume_delivered(o, delivered)
            continue

        try:
            status = _poll_vendor(o, gid)  # may set shipped
        except Exception:  # noqa: BLE001
            continue
        tn = status.get("tracking_number", "")
        gstatus = (status.get("status") or "").lower()

        # First appearance of tracking: stamp the ship date for every channel,
        # and push carrier + tracking to the Etsy buyer when there is one.
        if tn and not had_tracking:
            newly_shipped.append(o["order_id"])
            if not o.get("shipped_at"):
                from datetime import datetime as _dt
                update_order(o["order_id"], shipped_at=_dt.now().isoformat())
            if o.get("etsy_order_id"):
                try:
                    from quoteforge.automation.etsy_api import create_receipt_shipment
                    create_receipt_shipment(
                        o["etsy_order_id"], tn,
                        # `or "other"`: vendors may send carrier as '' (key
                        # present but empty), which Etsy would reject.
                        carrier_name=status.get("carrier") or "other")
                    pushed.append(o["order_id"])
                except Exception:  # noqa: BLE001
                    pass

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
    """Render the sync result counts as a short plain-text block."""
    return ("Fulfillment tracking sync\n" + "-" * 34 + "\n"
            f"  Newly shipped : {len(r['newly_shipped'])}\n"
            f"  Pushed to Etsy: {len(r['pushed_to_etsy'])}\n"
            f"  Delivered     : {len(r['delivered'])}")
