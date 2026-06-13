"""Design save + accept + sale notifications + order intake.

When the customer completes an order on the storefront (their FINAL approval),
we: record the acceptance against their saved design, email the customer a
confirmation, ALERT THE OWNER (a sale is never silent), and - when shipping
details were collected - create a real order record so the standard
fulfillment flow takes over (visible in the daily report, briefing, pipeline).
"""
from __future__ import annotations

import hashlib
import json


def _email_body(email: str, summary: str) -> str:
    """Customer confirmation email body - AI-personalized when available,
    deterministic template otherwise."""
    try:
        from quoteforge.ai.assistant import ai_text
        txt = ai_text(
            "Write a short, warm confirmation email body (3-4 sentences, no subject) "
            "to a customer who just gave final approval on their personalized "
            "wall-art order. Thank them, confirm their design and details are "
            "saved and the order is moving to production, and invite them to "
            "reply right away if anything needs changing. Do not invent "
            f"prices or dates. Their order:\n{summary}", "design_confirmation",
            max_tokens=200)
        if txt and txt.strip():
            return txt.strip()
    except Exception:  # noqa: BLE001
        pass
    return ("Thank you - your order is confirmed! Here's what you approved:\n\n"
            f"{summary}\n\n"
            "Your design and details are saved and your order is moving to "
            "production. Need to change the wording, photo, frame or layout? "
            "Reply to this email right away and we'll take care of it.")


def _parse_design(design_json: str) -> dict:
    """The full design payload dict (contact + cart) the storefront sends."""
    try:
        return json.loads(design_json or "{}") or {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_contact(design_json: str) -> dict:
    """The ship-to/contact block the storefront nests inside the design payload."""
    return _parse_design(design_json).get("contact") or {}


def _cart_money(design_json: str) -> dict:
    """The recorded basket money: sale_price, item_count, line_items (JSON).
    Empty when the storefront sent no cart (older clients) so nothing breaks."""
    cart = _parse_design(design_json).get("cart") or {}
    lines = cart.get("lines") or []
    money: dict = {}
    try:
        if cart.get("subtotal") is not None:
            money["sale_price"] = round(float(cart["subtotal"]), 2)
    except (TypeError, ValueError):
        pass
    if cart.get("items") is not None:
        try:
            money["item_count"] = int(cart["items"])
        except (TypeError, ValueError):
            pass
    elif lines:
        money["item_count"] = sum(int(l.get("qty", 1) or 1) for l in lines)
    if lines:
        money["line_items"] = json.dumps(lines)
    return money


def _alert_owner(email: str, summary: str, contact: dict) -> None:
    """Email the OWNER that a storefront sale completed (never raises)."""
    try:
        from quoteforge.automation.emailer import _send_email
        ship = ", ".join(filter(None, [
            contact.get("name"), contact.get("addr"), contact.get("city"),
            contact.get("state"), contact.get("zip"), contact.get("country")]))
        html = ("<html><body style='font-family:Arial'>"
                "<h3>New storefront order completed</h3>"
                f"<p><b>Customer:</b> {email}"
                + (f"<br><b>Phone:</b> {contact.get('phone')}" if contact.get("phone") else "")
                + (f"<br><b>Ship to:</b> {ship}" if ship else "")
                + "</p><pre style='background:#f6f9f7;padding:10px;border-radius:8px'>"
                + f"{summary}</pre>"
                "<p>The order record is in QuoteForge - the fulfillment flow "
                "takes it from here (see the daily report / pipeline).</p>"
                "</body></html>")
        _send_email("\U0001F4B0 New storefront order - action: fulfil", html)
    except Exception:  # noqa: BLE001
        pass


def _intake_order(email: str, design_id: str, contact: dict,
                  money: dict = None) -> str:
    """Create the order record for a direct (non-marketplace) sale so the
    standard fulfillment flow takes over. Idempotent per (email, design_id);
    returns the order id, or '' when shipping details are missing. ``money``
    carries the recorded basket (sale_price, item_count, line_items)."""
    if not (contact.get("name") and contact.get("addr")):
        return ""
    try:
        from quoteforge.db.database import create_order, get_order
        oid = "WEB-" + hashlib.sha1(
            f"{email}|{design_id}".encode("utf-8")).hexdigest()[:10].upper()
        if not get_order(oid):
            create_order({"order_id": oid,
                          "recipient_name": contact.get("name"),
                          "customer_name": contact.get("name"),
                          "customer_email": email,
                          "occasion": "Personalized order",
                          "channel": "direct",
                          # The recorded basket - so the ledger/reconciliation
                          # see REAL revenue + item count (was sale_price=None).
                          **(money or {})})
        return oid
    except Exception:  # noqa: BLE001
        return ""


def confirm_design(email: str, summary: str = "", design_json: str = "",
                   design_id: str = "default", send: bool = True) -> dict:
    """Record the customer's final approval: save + accept the design, alert
    the owner, create the order record (when ship-to details are present),
    and (optionally) email the customer a confirmation."""
    from quoteforge.db.database import init_db, save_design, accept_design
    init_db()
    email = (email or "").strip().lower()
    if "@" not in email:
        return {"ok": False, "error": "valid email required", "emailed": False,
                "order_id": ""}
    contact = _parse_contact(design_json)
    money = _cart_money(design_json)
    order_id = _intake_order(email, design_id, contact, money)
    save_design(email, design_json=design_json, design_id=design_id,
                summary=summary, order_id=order_id)
    accept_design(email, design_id)
    _alert_owner(email, summary or "(no summary)", contact)
    emailed = False
    if send:
        try:
            from quoteforge.automation.emailer import _send_email
            body = _email_body(email, summary or "(your personalized design)")
            html = ("<html><body style='font-family:Arial'>"
                    f"<p>{body.replace(chr(10), '<br>')}</p></body></html>")
            _send_email("Your Joffiels order is confirmed", html, to=email)
            emailed = True
        except Exception:  # noqa: BLE001
            emailed = False
    return {"ok": True, "emailed": emailed, "order_id": order_id}
