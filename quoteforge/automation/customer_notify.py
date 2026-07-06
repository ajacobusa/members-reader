"""Transactional customer notifications (audit #16b) - a personal-touch order update.

OFF by default (CUSTOMER_AUTO_NOTIFY). The marketplace already sends an order
confirmation and the shipped+tracking notice is auto-sent elsewhere, so this only
adds the updates the marketplace does NOT send - "Order Received" (confirming the
exact approved design), "In Production", and "Order Delivered" (a delivery
confirmation with the 7-day photo-coverage reminder) - and only when the owner opts in.

Best-practice guarantees:
  - idempotent: a message is marked sent only after a real send, so it never double-sends
  - no leak: a body that somehow names a supplier/marketplace is skipped, never sent
  - TEST_MODE / disabled: a hard no-op (never sends during tests or when off)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Only these are auto-sent. NOT "Order Shipped" (already pushed with tracking) nor
# "Proof Ready"/"Review Request" (handled by their own flows).
AUTO_TYPES = ("Order Received", "In Production", "Order Delivered")

# Never let a supplier or the marketplace name reach the customer.
_BANNED = ("gelato", "printify", "printful", "etsy")

_SUBJECTS = {
    "Order Received": "Your order is confirmed \U0001F49B",
    "In Production": "Your personalized piece is being made ✨",
    "Order Delivered": "Your order has arrived \U0001F389",
}


def queue_order_delivered(order_id: str, recipient_name: str = "") -> bool:
    """Queue the buyer 'Order Delivered' notice ONCE (idempotent - skips if already
    queued for this order). Queued regardless of the opt-in so it's ready; it is only
    SENT by the gated send_pending_notifications sweep. Best-effort: never raises into
    the delivery/tracking flow."""
    try:
        from quoteforge.db.database import get_customer_messages, save_customer_message
        from quoteforge.etsy.customer_messages import get_base_template
        if any(m.get("message_type") == "Order Delivered"
               for m in get_customer_messages(order_id)):
            return False                         # already queued - no duplicate notice
        save_customer_message(order_id, "Order Delivered",
                              get_base_template("Order Delivered"), sent=False)
        return True
    except Exception as exc:  # noqa: BLE001 - a queue hiccup never blocks delivery processing
        logger.warning("queue_order_delivered failed for %s: %s", order_id, exc)
        return False


def _leaks(body: str) -> bool:
    """True if the message body names a supplier or the marketplace (never send it)."""
    low = (body or "").lower()
    return any(b in low for b in _BANNED)


def send_pending_notifications() -> dict:
    """Send the opt-in transactional updates. Returns a summary; a hard no-op when
    disabled or in TEST_MODE."""
    from quoteforge.config import CUSTOMER_AUTO_NOTIFY, TEST_MODE
    if not CUSTOMER_AUTO_NOTIFY or TEST_MODE:
        return {"enabled": False, "sent": [], "skipped": []}
    from quoteforge.db.database import (init_db, pending_customer_messages,
                                        mark_message_sent)
    from quoteforge.automation.emailer import _send_email
    init_db()
    sent, skipped = [], []
    for m in pending_customer_messages(AUTO_TYPES):
        body = m.get("message_body") or ""
        if _leaks(body):
            logger.warning("notify: skipped msg %s (supplier/marketplace name in body)",
                           m["id"])
            skipped.append(m["id"])
            continue
        subject = _SUBJECTS.get(m["message_type"], "An update on your order")
        html = ("<html><body style='font-family:Arial;font-size:15px'>"
                f"<p>Hi {m.get('recipient_name') or 'there'},</p>"
                f"<p>{body}</p></body></html>")
        try:
            res = _send_email(subject, html, to=m["customer_email"],
                              critical=True, bcc_owner=False)   # buyer transactional: priority
        except Exception as exc:  # noqa: BLE001 - one bad address never blocks the rest
            logger.error("notify: send failed for %s: %s", m["order_id"], exc)
            skipped.append(m["id"])
            continue
        if res.get("status") == "sent":
            mark_message_sent(m["id"])     # idempotent: only after a real send
            sent.append(m["id"])
        else:
            skipped.append(m["id"])        # not sent (no creds) -> retry next run
    logger.info("notify: sent=%d skipped=%d", len(sent), len(skipped))
    return {"enabled": True, "sent": sent, "skipped": skipped}
