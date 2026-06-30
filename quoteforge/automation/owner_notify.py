"""Owner per-order notices to ORDER_NOTIFY_EMAIL:
  - an INVOICE copy when an order is PLACED (send_owner_invoice), and
  - a SHIPPED + tracking copy when it SHIPS (send_owner_shipped).

Idempotent: each is guarded by a per-order DB flag (owner_invoice_emailed /
owner_shipped_emailed) so a duplicate webhook or a re-poll can NEVER double-send.
Best-effort: a send failure never blocks order creation or tracking - it logs loudly
and, because the flag is only set on a confirmed send, the next run retries instead of
losing the notice. This is the OWNER inbox (internal), so cost/vendor detail is fine.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _order(order) -> dict:
    """Fetch the freshest order row (so flags are current); fall back to a passed dict."""
    from quoteforge.db.database import get_order
    if isinstance(order, dict):
        return get_order(order.get("order_id")) or order
    return get_order(order) or {}


def _money(v) -> str:
    """Format a value as USD, or an em-dash when it isn't a number."""
    try:
        return f"${float(v):.2f}"
    except (TypeError, ValueError):
        return "—"


def _item_line(o: dict) -> str:
    """One human description of what was ordered."""
    bits = [str(o.get(k)) for k in ("product_type", "material", "size")
            if o.get(k)]
    desc = " · ".join(bits) or (o.get("listing") or "Custom item")
    qty = int(o.get("quantity") or 1)
    return f"{desc} ×{qty}" if qty > 1 else desc


def tracking_url(carrier: str, tracking_number: str) -> str:
    """A universal tracking link (resolves any carrier from the number)."""
    if not tracking_number:
        return ""
    return f"https://t.17track.net/en#nums={tracking_number}"


def _invoice_html(o: dict) -> str:
    """The owner invoice email body for a placed order."""
    rows = [
        ("Order", o.get("order_id", "")),
        ("Placed", o.get("created_at") or ""),
        ("Customer", o.get("customer_name") or o.get("recipient_name") or "—"),
        ("Email", o.get("customer_email") or "—"),
        ("Customer ID", o.get("customer_id") or "—"),
        ("Item", _item_line(o)),
        ("Occasion", o.get("occasion") or "—"),
        ("Item price", _money(o.get("sale_price"))),
        ("Shipping", _money(o.get("shipping_collected"))),
    ]
    body = "".join(
        f"<tr><td style='padding:3px 12px 3px 0;color:#667'>{k}</td>"
        f"<td style='padding:3px 0'><b>{v}</b></td></tr>" for k, v in rows)
    return ("<div style='font-family:system-ui,Arial;font-size:14px'>"
            "<h2 style='margin:0 0 8px'>🧾 New order received</h2>"
            f"<table>{body}</table></div>")


def _shipped_html(o: dict) -> str:
    """The owner shipped email body, including the carrier + tracking link."""
    tn = o.get("tracking_number") or ""
    carrier = o.get("carrier") or ""
    url = tracking_url(carrier, tn)
    link = (f"<a href='{url}'>{tn}</a>" if url else (tn or "—"))
    rows = [
        ("Order", o.get("order_id", "")),
        ("Customer", o.get("customer_name") or o.get("recipient_name") or "—"),
        ("Shipped", _item_line(o)),
        ("Carrier", carrier or "—"),
        ("Tracking", link),
    ]
    body = "".join(
        f"<tr><td style='padding:3px 12px 3px 0;color:#667'>{k}</td>"
        f"<td style='padding:3px 0'><b>{v}</b></td></tr>" for k, v in rows)
    return ("<div style='font-family:system-ui,Arial;font-size:14px'>"
            "<h2 style='margin:0 0 8px'>📦 Order shipped</h2>"
            f"<table>{body}</table></div>")


def _delivered_html(o: dict) -> str:
    """The owner delivered-confirmation email body."""
    tn = o.get("tracking_number") or ""
    rows = [
        ("Order", o.get("order_id", "")),
        ("Customer", o.get("customer_name") or o.get("recipient_name") or "—"),
        ("Delivered", _item_line(o)),
        ("Delivered at", o.get("delivered_at") or "—"),
        ("Tracking", tn or "—"),
    ]
    body = "".join(
        f"<tr><td style='padding:3px 12px 3px 0;color:#667'>{k}</td>"
        f"<td style='padding:3px 0'><b>{v}</b></td></tr>" for k, v in rows)
    return ("<div style='font-family:system-ui,Arial;font-size:14px'>"
            "<h2 style='margin:0 0 8px'>✅ Order delivered</h2>"
            f"<table>{body}</table></div>")


def _send(subject: str, html: str) -> dict:
    """Send one owner notice to ORDER_NOTIFY_EMAIL via the Gmail SMTP sender."""
    from quoteforge.config import ORDER_NOTIFY_EMAIL
    from quoteforge.automation.emailer import _send_email
    return _send_email(subject, html, to=ORDER_NOTIFY_EMAIL)


def _notify(order, flag: str, subject_fn, html_fn) -> dict:
    """Shared idempotent + best-effort send: skip if already flagged, set the flag only
    on a confirmed send, never raise."""
    from quoteforge.db.database import update_order
    o = _order(order)
    oid = o.get("order_id")
    if not oid:
        return {"status": "skipped", "message": "no order id"}
    if o.get(flag):
        return {"status": "already_sent", "order_id": oid}
    try:
        res = _send(subject_fn(o), html_fn(o))
    except Exception as exc:  # noqa: BLE001 - never block the order/tracking flow
        logger.warning("owner notice (%s) for %s failed to send (will retry next "
                       "run): %s", flag, oid, exc)
        return {"status": "error", "order_id": oid, "message": str(exc)}
    if res.get("status") == "sent":
        try:
            update_order(oid, **{flag: 1})
        except Exception as exc:  # noqa: BLE001 - sent but flag not stored: a re-run
            # could re-send. Log LOUDLY rather than silently risk a duplicate notice.
            logger.warning("owner notice (%s) for %s SENT but flag not stored - a "
                           "re-run may re-send: %s", flag, oid, exc)
    else:
        logger.warning("owner notice (%s) for %s not sent (%s); will retry next run",
                       flag, oid, res.get("message") or res.get("status"))
    return res


def send_owner_invoice(order) -> dict:
    """Email the owner an invoice copy when an order is placed (idempotent, best-effort)."""
    return _notify(order, "owner_invoice_emailed",
                   lambda o: f"🧾 New order {o.get('order_id','')} — invoice",
                   _invoice_html)


def send_owner_shipped(order) -> dict:
    """Email the owner a shipped + tracking copy when an order ships (idempotent)."""
    return _notify(order, "owner_shipped_emailed",
                   lambda o: f"📦 Shipped {o.get('order_id','')} — "
                             f"{o.get('tracking_number','') or 'tracking'}",
                   _shipped_html)


def send_owner_delivered(order) -> dict:
    """Email the owner when an order is confirmed delivered (idempotent, best-effort)."""
    return _notify(order, "owner_delivered_emailed",
                   lambda o: f"✅ Delivered {o.get('order_id','')}",
                   _delivered_html)
