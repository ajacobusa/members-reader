"""Fulfillment tracking sync - the order->delivery link, validated end to end.

For every in-production/shipped order: poll its vendor (Gelato, Printify, or
Printful - chosen by the order's `vendor` column) for tracking, advance the
order to 'shipped', and push the carrier + tracking number to the Etsy buyer.

Delivery is validated, not assumed blindly:
  - Gelato reports delivery -> status 'delivered', delivery_confirmed=1 (REAL).
  - Printify/Printful order APIs never report delivery, so their shipped orders
    are ASSUMED delivered ASSUME_DELIVERED_DAYS after shipping ->
    delivery_confirmed=0 (clearly distinguishable from a real delivery).

Robustness:
  - The buyer shipped-notification is gated on `buyer_notified`, not on whether
    tracking exists - so a FAILED push retries next run instead of being lost.
  - Vendor poll errors are LOGGED to pipeline_log and counted (not swallowed).
  - Orders that sit past STUCK_AFTER_DAYS with no tracking are returned in a
    `stuck` list so they can be chased instead of quietly dying.
  - A tracked order missing `shipped_at` gets it backfilled so the assumed-
    delivery clock can actually start.

The vendor order id is read from `vendor_order_id` with `gelato_order_id` as
the legacy fallback for old rows. Scheduled; TEST_MODE-safe.
"""
from __future__ import annotations

# Printify/Printful don't report delivery; assume it this many days after the
# ship date (domestic parcels arrive in 2-8 days; 14 is a safe outer bound).
ASSUME_DELIVERED_DAYS = 14

# An order submitted to a vendor that still has no tracking after this many
# days is "stuck" (vendor error, lost, no key) and needs a human.
STUCK_AFTER_DAYS = 10

# Vendors whose order API stops giving new information once tracking exists.
_NO_DELIVERY_SIGNAL = ("printify", "printful")

# Statuses that mean the order is done / not awaiting a delivery update.
_TERMINAL = ("delivered", "cancelled", "refunded")


def _now_iso() -> str:
    """Current timestamp (ISO-8601)."""
    from datetime import datetime as _dt
    return _dt.now().isoformat()


def _age_days(ts: str) -> float | None:
    """Whole days since an ISO timestamp, or None when it can't be parsed."""
    from datetime import datetime as _dt
    try:
        return (_dt.now() - _dt.fromisoformat(ts)).days
    except (ValueError, TypeError):
        return None


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


def _backfill_shipped_at(order: dict) -> None:
    """Stamp shipped_at on a tracked order missing it, so the assumed-delivery
    clock can start (legacy rows / writes by another path can leave it blank)."""
    if order.get("shipped_at"):
        return
    from quoteforge.db.database import update_order
    ts = order.get("updated_at") or _now_iso()
    update_order(order["order_id"], shipped_at=ts)
    order["shipped_at"] = ts


def _retry_buyer_push(order: dict, pushed: list, carrier: str = "") -> None:
    """Push tracking to the Etsy buyer if not yet done. Idempotent: gated on
    `buyer_notified`, so a failed push retries next run instead of being lost."""
    tn = order.get("tracking_number") or ""
    if not (tn and order.get("etsy_order_id")) or order.get("buyer_notified"):
        return
    try:
        from quoteforge.automation.etsy_api import create_receipt_shipment
        # vendors may send carrier as '' (key present, empty) which Etsy rejects
        create_receipt_shipment(order["etsy_order_id"], tn,
                                 carrier_name=carrier or "other")
    except Exception as exc:  # noqa: BLE001
        from quoteforge.db.database import log_pipeline_stage
        log_pipeline_stage(order["order_id"], "buyer_notify", "error", str(exc))
        return                       # not marked notified -> retried next run
    from quoteforge.db.database import update_order
    update_order(order["order_id"], buyer_notified=1)
    order["buyer_notified"] = 1
    pushed.append(order["order_id"])


def _carrier_confirm(order: dict, delivered_confirmed: list) -> str:
    """Poll the carrier (tracking API) for a tracked order of ANY vendor. On a
    real 'delivered' scan, mark the order carrier-confirmed (delivery_confirmed
    =1) and append it. Returns the carrier state ('delivered'/'in_transit'/
    'exception') or '' when no API/tracking/usable answer."""
    from quoteforge.config import TRACKING_API_KEY
    if not (TRACKING_API_KEY and order.get("tracking_number")):
        return ""
    from quoteforge.fulfillment.tracking_api import carrier_status
    st = carrier_status(order["tracking_number"], order.get("carrier") or "")
    if st == "delivered":
        from quoteforge.db.database import update_order
        update_order(order["order_id"], status="delivered",
                     delivery_confirmed=1,
                     delivered_at=order.get("delivered_at") or _now_iso())
        delivered_confirmed.append(order["order_id"])
    return st or ""


def _confirm_or_assume_delivery(order: dict, delivered_confirmed: list,
                                delivered_assumed: list) -> None:
    """Resolve delivery for a Printify/Printful order (which never report
    delivery themselves): carrier-confirm first, else the timer ASSUMPTION."""
    st = _carrier_confirm(order, delivered_confirmed)
    if st in ("delivered", "in_transit", "exception"):
        return                      # carrier is authoritative - trust it
    # No carrier data -> timer assumption (these vendors have no signal at all).
    age = _age_days(order.get("shipped_at") or "")
    if age is None or age < ASSUME_DELIVERED_DAYS:
        return
    from quoteforge.db.database import update_order
    update_order(order["order_id"], status="delivered", delivery_confirmed=0,
                 delivered_at=order.get("delivered_at") or _now_iso())
    delivered_assumed.append(order["order_id"])


def _is_stuck(order: dict) -> bool:
    """True when an order submitted to a vendor still has no tracking long past
    the production+ship SLA (it needs a human, not another silent skip)."""
    if order.get("tracking_number"):
        return False
    age = _age_days(order.get("created_at") or order.get("updated_at") or "")
    return age is not None and age >= STUCK_AFTER_DAYS


def sync_tracking(limit: int = 500) -> dict:
    """Poll vendors for all open orders, advance statuses, push tracking to the
    buyer (idempotently), confirm or assume delivery, and surface stuck orders."""
    from quoteforge.db.database import (init_db, get_all_orders, update_order,
                                        log_pipeline_stage)
    init_db()
    newly_shipped, pushed, stuck = [], [], []
    delivered_confirmed, delivered_assumed = [], []
    errors = 0
    for o in get_all_orders(limit):
        gid = o.get("vendor_order_id") or o.get("gelato_order_id")
        if not gid or o.get("status") in _TERMINAL:
            continue
        vendor = (o.get("vendor") or "gelato").lower()
        had_tracking = bool(o.get("tracking_number"))

        # Printify/Printful with known tracking: nothing new to poll - keep the
        # buyer notified (retry), backfill the ship date, age toward delivery.
        if vendor in _NO_DELIVERY_SIGNAL and had_tracking:
            _backfill_shipped_at(o)
            _retry_buyer_push(o, pushed)
            _confirm_or_assume_delivery(o, delivered_confirmed, delivered_assumed)
            continue

        try:
            status = _poll_vendor(o, gid)  # may set shipped
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log_pipeline_stage(o["order_id"], "tracking_sync", "error", str(exc))
            if _is_stuck(o):
                stuck.append(o["order_id"])
            continue

        tn = status.get("tracking_number", "")
        gstatus = (status.get("status") or "").lower()

        if tn and not had_tracking:
            newly_shipped.append(o["order_id"])
            carrier = status.get("carrier") or ""
            eta = status.get("estimated_delivery") or ""
            fields = {} if o.get("shipped_at") else {"shipped_at": _now_iso()}
            if carrier and carrier != (o.get("carrier") or ""):
                fields["carrier"] = carrier
                o["carrier"] = carrier
            if eta and eta != (o.get("estimated_delivery") or ""):
                fields["estimated_delivery"] = eta
            if fields:
                update_order(o["order_id"], **fields)
                o.setdefault("shipped_at", fields.get("shipped_at"))
        if tn:
            o["tracking_number"] = tn
            _retry_buyer_push(o, pushed, carrier=status.get("carrier", ""))

        if gstatus == "delivered":   # vendor (Gelato) reported delivery directly
            update_order(o["order_id"], status="delivered", delivery_confirmed=1,
                         delivered_at=o.get("delivered_at") or _now_iso())
            delivered_confirmed.append(o["order_id"])
        elif o.get("tracking_number"):
            # Has tracking but the vendor hasn't confirmed delivery (Gelato often
            # only reports 'shipped') -> ask the CARRIER. No timer for Gelato:
            # it stays shipped until a real delivered scan, never falsely +.
            _carrier_confirm(o, delivered_confirmed)
        elif not tn and _is_stuck(o):
            stuck.append(o["order_id"])

    return {
        "checked": True,
        "newly_shipped": newly_shipped,
        "pushed_to_etsy": pushed,
        "delivered_confirmed": delivered_confirmed,
        "delivered_assumed": delivered_assumed,
        # Back-compat: combined delivered list (confirmed + assumed).
        "delivered": delivered_confirmed + delivered_assumed,
        "stuck": stuck,
        "errors": errors,
    }


def format_tracking_text(r: dict) -> str:
    """Render the sync result counts as a short plain-text block."""
    lines = ["Fulfillment tracking sync", "-" * 34,
             f"  Newly shipped    : {len(r['newly_shipped'])}",
             f"  Pushed to Etsy   : {len(r['pushed_to_etsy'])}",
             f"  Delivered (conf) : {len(r.get('delivered_confirmed', []))}",
             f"  Delivered (assum): {len(r.get('delivered_assumed', []))}"]
    if r.get("stuck"):
        lines.append(f"  STUCK (no track) : {len(r['stuck'])} -> {', '.join(r['stuck'][:5])}")
    if r.get("errors"):
        lines.append(f"  Poll errors      : {r['errors']}")
    return "\n".join(lines)
