"""Claim decision automation - the end-to-end link from a validated request to
an actual resolution.

Once a claim reaches ``supplier_review`` (validated against the order + evidence),
the owner records the decision and the system acts on it:
  * approved_reprint -> auto-create the Gelato replacement order (reusing the
    original artwork, product, and stored ship-to) and email the customer.
  * approved_refund  -> mark for refund + email the customer (the marketplace
    issues the actual refund; we document and notify).
  * denied / needs_more_info -> email the customer the reason / what's missing.

State transitions are enforced by the claim_service state machine. Customer
emails BCC the owner and skip gracefully when email isn't configured.
"""
import json
import logging

from quoteforge.fulfillment.claim_service import advance_claim

_logger = logging.getLogger(__name__)


def open_claims(states: list = None) -> list:
    """All orders with a claim on record (the review queue), optionally filtered
    to specific claim states (e.g. ['supplier_review', 'needs_more_info'])."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    out = [o for o in get_all_orders(100000) if o.get("claim_status")]
    if states:
        out = [o for o in out if o.get("claim_status") in states]
    return out


def create_replacement_order(order: dict) -> dict:
    """Create a Gelato replacement (reprint) for a claimed order, reusing the
    original artwork, product UID, and stored ship-to. Returns the routing
    result; status 'needs_input' when the artwork/product/address is missing."""
    recipient = {}
    if order.get("ship_to"):
        try:
            recipient = json.loads(order["ship_to"])
        except (ValueError, TypeError):
            recipient = {}
    recipient = recipient or order.get("recipient_address") or {}
    artwork = order.get("artwork_url") or order.get("print_file") or ""
    product_uid = order.get("gelato_product_uid") or order.get("product_uid") or ""
    missing = [n for n, v in (("ship_to", recipient), ("artwork", artwork),
                              ("product_uid", product_uid)) if not v]
    if missing:
        return {"status": "needs_input", "missing": missing,
                "detail": "cannot auto-reprint - " + ", ".join(missing) + " missing"}
    from quoteforge.fulfillment.router import route_order
    return route_order(
        {"order_id": str(order.get("order_id")) + "-R", "vendor": "gelato",
         "gelato_product_uid": product_uid},
        recipient=recipient, artwork_url=artwork)


def _email_customer(order: dict, subject: str, body: str) -> dict:
    """Send a customer-facing claim email (BCCs the owner; skips without SMTP)."""
    to = order.get("customer_email") or ""
    if not to:
        return {"status": "skipped", "message": "no customer email on order"}
    try:
        from quoteforge.automation.emailer import _send_email
        return _send_email(subject, body, to=to)
    except Exception as exc:  # noqa: BLE001 - notification must never crash the decision
        return {"status": "error", "message": str(exc)}


def _decision_email(order: dict, decision: str, note: str) -> tuple:
    """Build the (subject, html) customer message for a decision."""
    name = order.get("recipient_name") or order.get("customer_name") or "there"
    if decision == "approved_reprint":
        return ("Your replacement is on the way 💚",
                f"<p>Hi {name}, great news - we've approved a free replacement "
                "for your order and it's heading to production now. There's no "
                "need to return the original; please keep or recycle it. We'll "
                "email tracking as soon as it ships.</p>")
    if decision == "approved_refund":
        return ("Your refund is being processed",
                f"<p>Hi {name}, we've approved a refund for your order. You'll "
                "see it back on your original payment method shortly. Thank you "
                "for your patience, and we're sorry for the trouble.</p>")
    if decision == "needs_more_info":
        extra = f" Specifically: {note}." if note else ""
        return ("A quick bit more info on your request",
                f"<p>Hi {name}, thanks for your request. To review it we need a "
                f"little more from you.{extra} Just reply with the details or "
                "photos and we'll get right on it.</p>")
    # denied
    reason = f" {note}" if note else ""
    return ("About your recent request",
            f"<p>Hi {name}, thank you for reaching out. After reviewing your "
            f"order we're unable to approve a free replacement or refund in this "
            f"case.{reason} Because each piece is custom-made from the design "
            "approved at checkout, we're limited on change-of-mind or approved-"
            "content issues - but please reply if you'd like a discounted "
            "reprint and we'll help however we can.</p>")


def decide_claim(order_id: str, decision: str, note: str = "",
                 send: bool = False) -> dict:
    """Record a claim decision and act on it (enforcing the state machine).

    decision: approved_reprint | approved_refund | denied | needs_more_info, or
    an intermediate state (validating_order/evidence_review/supplier_review).
    On approved_reprint the Gelato replacement is created automatically. When
    ``send`` is true the customer is emailed the outcome. Returns
    {ok, status, replacement, email, reason}.
    """
    from quoteforge.db.database import get_order, update_order
    order = get_order(order_id)
    if not order:
        return {"ok": False, "reason": "order not found", "replacement": None,
                "email": None}
    current = order.get("claim_status") or "new"
    move = advance_claim(current, decision)
    if not move["ok"]:
        return {"ok": False, "reason": move["reason"], "replacement": None,
                "email": None}

    update_order(order_id, claim_status=decision,
                 claim_resolution=note or order.get("claim_resolution") or "")
    result = {"ok": True, "status": decision, "replacement": None, "email": None}

    if decision == "approved_reprint":
        rep = create_replacement_order(order)
        result["replacement"] = rep
        if rep.get("status") == "submitted" and rep.get("id"):
            update_order(order_id, replacement_order_id=rep["id"])

    if send and decision in ("approved_reprint", "approved_refund", "denied",
                             "needs_more_info"):
        subject, body = _decision_email(order, decision, note)
        result["email"] = _email_customer(order, subject, body)
    return result


# Claim states that still need owner action (vs. terminal approved/denied).
ACTIONABLE_STATES = ["new", "validating_order", "evidence_review",
                     "supplier_review", "needs_more_info"]


def run_claims_digest(send: bool = False) -> dict:
    """Owner digest of claims still needing action. Emails the owner when there
    are any (and ``send`` is true). Returns {actionable, text}."""
    claims = open_claims(states=ACTIONABLE_STATES)
    text = format_claims_queue(states=ACTIONABLE_STATES)
    if send and claims:
        try:
            from quoteforge.automation.emailer import _send_email
            out = _send_email(f"⚠️ {len(claims)} claim(s) need attention",
                              "<pre>" + text + "</pre>")
            if isinstance(out, dict) and out.get("status") not in ("sent", "ok"):
                _logger.warning("claims-digest alert not delivered: %s", out)
        except Exception as exc:  # noqa: BLE001 - alert must not block, but log it
            _logger.warning("claims-digest alert failed to send: %s", exc)
    return {"actionable": len(claims), "text": text}


def format_claims_queue(states: list = None) -> str:
    """Render the open-claims queue as owner-facing console text."""
    claims = open_claims(states)
    if not claims:
        return "No open claims." + (f" (states={states})" if states else "")
    lines = ["=" * 60, f"CLAIM QUEUE ({len(claims)})", "=" * 60]
    for o in sorted(claims, key=lambda x: x.get("claim_status") or ""):
        lines.append(f"  {o['order_id']:<12} {o.get('claim_status',''):<18} "
                     f"{o.get('claim_category','') or '-':<18} "
                     f"{o.get('customer_email','') or ''}")
    lines.append("=" * 60)
    return "\n".join(lines)
