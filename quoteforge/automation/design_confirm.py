"""Design save + accept + sale notifications + order intake.

When the customer completes an order on the storefront (their FINAL approval),
we: record the acceptance against their saved design, save the approved proof
as a PDF evidence file under the order id (stored, NEVER emailed), ALERT THE
OWNER (a sale is never silent), and - when shipping details were collected -
create a real order record so the standard fulfillment flow takes over (visible
in the daily report, briefing, pipeline). No customer emails are sent here.
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
            "to a customer who just gave final, binding approval on their "
            "personalized wall-art order. Thank them, confirm the design they "
            "approved on screen is locked in exactly as shown and moving to "
            "production, and that because it is made to order it is now final. "
            "Invite them to reply only with a question or a delivery issue - do "
            "NOT invite design changes. Do not invent "
            f"prices or dates. Their order:\n{summary}", "design_confirmation",
            max_tokens=200)
        if txt and txt.strip():
            return txt.strip()
    except Exception:  # noqa: BLE001
        pass
    return ("Thank you - your order is confirmed! Here's what you approved on "
            "screen:\n\n"
            f"{summary}\n\n"
            "This is exactly what we'll print. Because each piece is made to "
            "order, your approval is final and it's now moving into production. "
            "Questions or a delivery issue? Just reply to this email and we're "
            "happy to help.")


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
                          # Ship-to destination for the shipping-variance audit.
                          "country": contact.get("country"),
                          "state": contact.get("state"),
                          # The recorded basket - so the ledger/reconciliation
                          # see REAL revenue + item count (was sale_price=None).
                          **(money or {})})
            # The on-screen approval at checkout IS the final, binding sign-off
            # (no emailed proof round). Record it immediately so the order carries
            # proof_approved + an audit timestamp - the dispute-evidence engine,
            # the post-approval field lock, and the production-without-approval
            # monitor all key off this. create_order's INSERT can't set proof
            # fields, so stamp them here (proof fields stay writable).
            from quoteforge.db.database import update_order
            from datetime import datetime as _dt
            update_order(oid, proof_approved=1,
                         proof_approved_at=_dt.now().isoformat(timespec="seconds"))
        return oid
    except Exception:  # noqa: BLE001
        return ""


def _save_proof_pdf(order_id: str, email: str, summary: str,
                    proof_image: str) -> str:
    """Render the on-screen approved proof to a PDF stored under the order id -
    the final approval evidence (stored, never emailed). Returns the path, or ''
    on any failure (evidence is best-effort and must never block confirmation)."""
    try:
        import base64
        import io
        from datetime import datetime as _dt
        from pathlib import Path
        from quoteforge.config import OUTPUT_DIR
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as _rl_canvas

        out_dir = Path(OUTPUT_DIR) / "proofs"
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / f"{order_id}_approved.pdf"
        _w, height = letter
        c = _rl_canvas.Canvas(str(pdf_path), pagesize=letter)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(inch, height - inch, "Approved proof - final approval record")
        c.setFont("Helvetica", 10)
        c.drawString(inch, height - 1.28 * inch, f"Order: {order_id}")
        c.drawString(inch, height - 1.48 * inch, f"Customer: {email}")
        c.drawString(inch, height - 1.68 * inch,
                     "Approved on screen: " + _dt.now().isoformat(timespec="seconds"))
        y = height - 2.0 * inch
        for line in (summary or "").splitlines()[:12]:
            c.drawString(inch, y, line[:92])
            y -= 0.18 * inch
        if isinstance(proof_image, str) and proof_image.startswith("data:image") \
                and "," in proof_image:
            raw = base64.b64decode(proof_image.split(",", 1)[1])
            img = ImageReader(io.BytesIO(raw))
            iw, ih = img.getSize()
            scale = min(1.0, (6.0 * inch) / iw) if iw else 1.0
            dw, dh = iw * scale, ih * scale
            c.drawImage(img, inch, max(0.8 * inch, (y - 0.2 * inch) - dh), dw, dh,
                        preserveAspectRatio=True, mask="auto")
        c.showPage()
        c.save()
        return str(pdf_path)
    except Exception:  # noqa: BLE001
        return ""


def confirm_design(email: str, summary: str = "", design_json: str = "",
                   design_id: str = "default", send: bool = True,
                   proof_image: str = "") -> dict:
    """Record the customer's final, binding approval: save + accept the design,
    create the order record (when ship-to details are present), save the
    approved proof as a PDF evidence file, and alert the owner. No customer
    email is sent - the on-screen approval + stored PDF is the record."""
    from quoteforge.db.database import init_db, save_design, accept_design
    init_db()
    email = (email or "").strip().lower()
    if "@" not in email:
        return {"ok": False, "error": "valid email required", "emailed": False,
                "order_id": "", "proof_pdf": ""}
    contact = _parse_contact(design_json)
    money = _cart_money(design_json)
    order_id = _intake_order(email, design_id, contact, money)
    save_design(email, design_json=design_json, design_id=design_id,
                summary=summary, order_id=order_id)
    accept_design(email, design_id)
    _alert_owner(email, summary or "(no summary)", contact)
    # Final approval EVIDENCE: store the on-screen approved proof as a PDF under
    # the order id. This is the record the made-to-order policy rests on; it is
    # stored, never emailed. No customer email is sent from this flow.
    proof_pdf = ""
    if order_id and proof_image:
        proof_pdf = _save_proof_pdf(order_id, email, summary, proof_image)
        if proof_pdf:
            try:
                from quoteforge.db.database import update_order
                update_order(order_id, proof_pdf=proof_pdf)
            except Exception:  # noqa: BLE001
                pass
    return {"ok": True, "emailed": False, "order_id": order_id,
            "proof_pdf": proof_pdf}
