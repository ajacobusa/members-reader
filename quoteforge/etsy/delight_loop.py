"""Delight loop - reviews + referrals in one post-delivery touch.

For a brand-new shop these are the two highest-leverage growth levers:
  * REVIEWS  drive Etsy search ranking AND buyer trust - the #1 thing a 0-review
    shop needs. The ask must land a few days AFTER delivery, at the satisfaction
    peak.
  * REFERRALS are the cheapest acquisition there is - a delighted gift-buyer
    knows other gift-buyers. A give-15 / get-15 offer turns each happy customer
    into a (free) acquisition channel.

This bundles both into ONE warm, specific message ~6 days after delivery, with a
thank-you coupon for their own next order. Idempotent (won't re-ask the same
order). Reads live orders so it works automatically as Joffiels grows.
"""
import hashlib
from datetime import datetime, timedelta

DELIGHT_LEAD_DAYS = 6          # send this many days after delivery (satisfaction peak)
# Extra days to wait before delighting an ASSUMED (not carrier-confirmed)
# delivery - so a Printify/Printful timer-delivery never asks for a review
# before the parcel has realistically arrived.
ASSUMED_DELIGHT_BUFFER_DAYS = 7
REVIEW_THANKYOU = "THANKYOU10"  # 10% off their own next order
REFERRAL_GIVE = 15             # friend gets this %
REFERRAL_GET = 15              # referrer gets this % on next order


def referral_code(customer_key: str) -> str:
    """A stable, shareable referral code unique to a customer."""
    h = hashlib.md5((customer_key or "guest").encode("utf-8")).hexdigest()[:5].upper()
    return f"JOFF{h}"


def _parse_dt(s: str) -> datetime:
    """Parse a timestamp string in any of the known formats; fall back to now."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime((s or "")[:19], fmt)
        except (ValueError, TypeError):
            continue
    return datetime.now()


def delight_message(order: dict) -> str:
    """Compose the combined review-ask + referral message for one order."""
    customer = order.get("customer_name") or "there"
    recipient = order.get("recipient_name") or "your recipient"
    occ = (order.get("occasion") or "gift").lower()
    key = order.get("customer_email") or order.get("customer_name") or "guest"
    code = referral_code(key)
    msg = (
        f"Hi {customer}! I hope {recipient} absolutely loved their personalized "
        f"{occ} gift.\n\n"
        f"If it brought a smile, a quick review would mean the world to a small "
        f"shop like Joffiels - honest reviews are what help others find us. As a "
        f"thank-you, here's 10% off your next order with code {REVIEW_THANKYOU}.\n\n"
        f"And if you know someone who'd love a personalized gift, share your code "
        f"{code} - they get {REFERRAL_GIVE}% off, and you get {REFERRAL_GET}% off "
        f"your next order too. Thank you for being part of Joffiels!"
    )
    return msg + _affiliate_block()


def _affiliate_block() -> str:
    """Optional 'complete the gift' affiliate links for the next occasion.
    Empty unless affiliate links are configured. Includes FTC disclosure."""
    try:
        from quoteforge.marketing.affiliate_programs import configured_links
        links = configured_links()
    except Exception:  # noqa: BLE001
        links = {}
    if not links:
        return ""
    lines = "\n".join(f"  - {label}: {url}" for label, url in links.items())
    return ("\n\n--\nPlanning the next celebration? Complete the gift:\n"
            f"{lines}\n"
            "(Some links are affiliate links - we may earn a small commission "
            "at no extra cost to you.)")


def _already_delighted(order_id: str) -> bool:
    """True if this order already has a recorded delight message (idempotency)."""
    from quoteforge.db.database import get_customer_messages
    return any(m.get("message_type") == "delight"
               for m in get_customer_messages(order_id))


def delight_due(orders: list[dict], now: datetime | None = None,
                lead_days: int = DELIGHT_LEAD_DAYS) -> list[dict]:
    """Orders delivered ~lead_days ago that haven't had the delight touch yet."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=lead_days)
    # Assumed deliveries (Printify/Printful timer, no carrier confirmation) wait
    # an extra buffer before we ask for a review - never nudge a customer who
    # may not actually have the item yet.
    assumed_cutoff = now - timedelta(days=lead_days + ASSUMED_DELIGHT_BUFFER_DAYS)
    due = []
    for o in orders:
        # A 'delivered' order is NOT automatically review-worthy. Suppress the
        # request when the order was refunded/cancelled, the delivery is
        # disputed (Etsy case/refund/complaint), or the owner opted it out.
        if o.get("status") in ("refunded", "cancelled"):
            continue
        if o.get("delivery_disputed") or o.get("do_not_request_review"):
            continue
        # A buyer who filed an in-app claim (damage/defect/lost/wrong-item) - regardless
        # of its outcome - must never get a 'leave a review' nudge. Only Etsy cases were
        # suppressed before (delivery_disputed), not our own claim flow.
        if (o.get("claim_status") or "").strip():
            continue
        # Owner manual confirmation counts as a confirmed delivery.
        manual = bool(o.get("manual_delivery_confirmed"))
        # A review is NEVER asked before delivery is confirmed. A bare "shipped"
        # status (tracking exists but the carrier has not reported delivery) is
        # in-transit and must not trigger the ask - only a "delivered" status or
        # an owner manual confirmation qualifies.
        if o.get("status") != "delivered" and not manual:
            continue
        # Anchor on ACTUAL delivery time (5-7 days after the parcel arrived),
        # else the last update, else created_at.
        ref = _parse_dt(o.get("delivered_at") or o.get("updated_at")
                        or o.get("created_at", ""))
        confirmed = (bool(o.get("delivery_confirmed")) or manual)
        if ref > (cutoff if confirmed else assumed_cutoff):
            continue                      # not enough time since delivery
        if _already_delighted(o.get("order_id", "")):
            continue
        key = o.get("customer_email") or o.get("customer_name") or "guest"
        due.append({
            "order_id": o.get("order_id", ""),
            "customer": o.get("customer_name", "Customer"),
            "recipient": o.get("recipient_name", ""),
            "referral_code": referral_code(key),
            "message": delight_message(o),
        })
    return due


def send_delight_touches(now: datetime | None = None, record: bool = True) -> dict:
    """Stage delight messages for all due orders (idempotent)."""
    from quoteforge.db.database import (
        init_db, get_all_orders, save_customer_message,
    )
    init_db()
    due = delight_due(get_all_orders(limit=100000), now)
    if record:
        for d in due:
            save_customer_message(d["order_id"], "delight", d["message"], sent=False)
    return {"due": len(due), "touches": due}


def format_delight_text(result: dict) -> str:
    """Render the delight-touch result as printable console text."""
    lines = ["=" * 60, "DELIGHT LOOP - reviews + referrals", "=" * 60,
             f"{result['due']} post-delivery touch(es) ready to send:"]
    for d in result["touches"][:15]:
        lines.append(f"\n  Order {d['order_id']} - {d['customer']} "
                     f"(referral {d['referral_code']})")
        lines.append(f"    {d['message'][:140]}...")
    if not result["touches"]:
        lines.append("  (none due - orders need ~6 days since delivery)")
    lines.append("=" * 60)
    return "\n".join(lines)


def send_delight_email(now: datetime | None = None) -> dict:
    """Stage due delight touches and email the digest to the shop owner."""
    result = send_delight_touches(now)
    if not result["due"]:
        return {"status": "no_action", "result": result}
    from quoteforge.automation.emailer import _send_email
    subject = f"Joffiels Delight Loop: {result['due']} review+referral touch(es) to send"
    body = (f"<html><body style='font-family:Arial'><pre style='font-size:13px'>"
            f"{format_delight_text(result)}</pre></body></html>")
    out = _send_email(subject, body)
    return {"status": out["status"], "result": result}
