"""Gift e-card line item + recipient email capture (a growth loop).

When a buyer adds a gift e-card to their order (recipient name + email + a short
message), we:
  1. send the recipient a one-time TRANSACTIONAL gift announcement (they expect
     it - the buyer chose to gift them), BCC the owner;
  2. capture the recipient's email into the subscriber list as source
     'gift_recipient' with consent='pending' - so every gift can recruit a new
     contact, but they only enter ongoing marketing once they OPT IN (compliant
     with CAN-SPAM / GDPR; the e-card includes an opt-in link + unsubscribe).

This turns one sale into a new lead at no ad cost. Never auto-markets to the
recipient until consent='yes'.
"""
from __future__ import annotations

import urllib.parse


def gift_fields(payload: dict) -> dict:
    """Extract gift-e-card fields from an order payload (any shape)."""
    return {
        "to_name": (payload.get("gift_recipient_name") or "").strip(),
        "to_email": (payload.get("gift_recipient_email") or "").strip(),
        "from_name": (payload.get("customer_name") or "Someone who cares").strip(),
        "message": (payload.get("gift_message") or "").strip(),
    }


def build_ecard_email(g: dict, shop: str, signup_url: str = "") -> tuple[str, str]:
    """Return (subject, html_body) for the recipient's gift announcement."""
    subject = f"🎁 {g['from_name']} sent you a gift from {shop}"
    msg = g["message"] or "Thinking of you - hope this brings a smile."
    opt = ""
    if signup_url:
        opt = (f'<p style="font-size:13px;color:#555">Want first access to new '
               f'designs &amp; a welcome offer? '
               f'<a href="{signup_url}">Join our list</a> (optional).</p>')
    body = (
        f'<div style="font-family:Georgia,serif;max-width:520px;margin:auto;'
        f'border:1px solid #e3ddd2;border-radius:12px;overflow:hidden">'
        f'<div style="background:#0f3d2e;color:#e8d8a8;padding:18px;'
        f'font-size:20px">{shop}</div>'
        f'<div style="padding:22px;color:#23302b">'
        f'<h2 style="color:#0f3d2e">Hi {g["to_name"] or "there"},</h2>'
        f'<p style="font-size:15px;line-height:1.6">{g["from_name"]} sent you a '
        f'personalized gift:</p>'
        f'<blockquote style="font-style:italic;color:#444;border-left:3px solid '
        f'#c9a84c;padding-left:12px">{msg}</blockquote>'
        f'<p style="font-size:14px;color:#555">Your personalized piece is being '
        f'made to order and will arrive soon.</p>{opt}'
        f'<p style="font-size:11px;color:#9aa39d">You received this one-time note '
        f'because {g["from_name"]} sent you a gift. You are not subscribed to any '
        f'list. Reply STOP to opt out of any future messages.</p>'
        f'</div></div>')
    return subject, body


def send_gift_ecard(payload: dict) -> dict:
    """If the order has gift-e-card fields, capture the recipient + send the
    e-card. Best-effort; never raises. Returns a small summary."""
    g = gift_fields(payload)
    if not g["to_email"] or "@" not in g["to_email"]:
        return {"sent": False, "reason": "no recipient email"}
    result = {"sent": False, "captured": False, "to": g["to_email"]}
    try:
        from quoteforge.db.database import add_subscriber, init_db
        init_db()
        result["captured"] = add_subscriber(
            g["to_email"], source="gift_recipient", consent="pending")
    except Exception:  # noqa: BLE001
        pass
    try:
        from quoteforge.config import SHOP_NAME, SIGNUP_URL
        from quoteforge.automation.emailer import _send_email
        subject, body = build_ecard_email(g, SHOP_NAME, SIGNUP_URL)
        _send_email(subject, body, to=g["to_email"])   # BCCs owner automatically
        result["sent"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result
