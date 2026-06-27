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




def _parse_design(design_json: str) -> dict:
    """The full design payload dict (contact + cart) the storefront sends."""
    try:
        return json.loads(design_json or "{}") or {}
    except Exception:  # noqa: BLE001
        return {}


def _parse_contact(design_json: str) -> dict:
    """The ship-to/contact block the storefront nests inside the design payload."""
    return _parse_design(design_json).get("contact") or {}


def _enrich_lines(lines: list) -> list:
    """Resolve each cart line's product IDENTITY (product_type, material, size,
    Gelato UID, gelato_cost) by reusing the marketplace path's enrichment, so a
    direct (/confirm) order is a COMPLETE, fulfillable, margin-checkable record - not
    a bare stub. The heavy per-line `design` is kept out of here (it lives on the
    saved design). Never raises; lazy import avoids a circular dependency."""
    out = []
    for line in lines:
        d = line.get("design") or {}
        item = {"recipient_name": "x", "occasion": "x",
                "material": line.get("fmt", ""),
                "product_size": line.get("size", ""), "size": line.get("size", ""),
                "custom_text": (d.get("wording") or "")}
        try:
            from quoteforge.automation.webhook_server import _build_order_data
            ed = _build_order_data(item, "")
        except Exception:  # noqa: BLE001
            ed = {}
        out.append({
            "title": line.get("title", ""), "fmt": line.get("fmt", ""),
            "size": ed.get("size") or line.get("size", ""), "unit": line.get("unit"),
            "qty": line.get("qty", 1), "placement": line.get("placement", ""),
            "logo": line.get("logo", ""), "cal": line.get("cal"),
            "product_type": ed.get("product_type"), "material": ed.get("material"),
            "product_uid": ed.get("gelato_product_uid"),
            "gelato_cost": ed.get("gelato_cost"), "color": ed.get("color")})
    return out


def _cart_money(design_json: str) -> dict:
    """The recorded basket money + product identity: sale_price, item_count, the
    enriched per-line list, AND the order's primary product fields (material, size,
    product_type, gelato_cost) so the direct order is fulfillable. Empty when the
    storefront sent no cart (older clients) so nothing breaks."""
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
        # Enrich each line with its resolved product identity (NOT the heavy design,
        # which lives on the saved design_json). This makes the direct order a
        # complete, fulfillable, margin-checkable record.
        enriched = _enrich_lines(lines)
        money["line_items"] = json.dumps(enriched)
        # Primary product fields from the first line so the ORDER row itself carries
        # product identity (was a bare stub: no material/size/type/cost -> unroutable
        # and invisible to the margin gate). Storefront orders are NOT routed to
        # Gelato here - the buyer pays on Etsy, whose webhook fulfils them.
        first = enriched[0]
        for k in ("material", "size", "product_type", "gelato_cost", "color"):
            if first.get(k) is not None:
                money[k] = first[k]
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
        return "", False
    try:
        from quoteforge.db.database import create_order, get_order
        # Idempotency key from the BASKET CONTENTS, not the per-click design_id
        # (the storefront sends design_id='cart-'+Date.now(), unique every submit,
        # so the get_order() dedup never matched). Now a repeated confirm of the
        # SAME basket resolves to the same WEB- id and is deduped server-side,
        # instead of creating a duplicate order (double alert, double revenue,
        # possible double print).
        import json
        cart_key = (json.dumps(money, sort_keys=True, default=str)
                    if money else design_id)
        oid = "WEB-" + hashlib.sha1(
            f"{email}|{cart_key}".encode("utf-8")).hexdigest()[:10].upper()
        created = False
        if not get_order(oid):
            created = True
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
        return oid, created
    except Exception:  # noqa: BLE001
        return "", False


def _save_proof_pdf(order_id: str, email: str, summary: str,
                    proof_image: str) -> str:
    """Render the on-screen approved proof to a PDF stored under the order id -
    the final approval evidence (stored, never emailed). Returns the path, or ''
    on any failure (evidence is best-effort and must never block confirmation).
    The proof image is size-capped and downscaled before embedding so a hostile
    or oversized data URL can't bloat memory or the stored file; the PDF is
    rendered in memory and only written on success (no orphaned partial file)."""
    try:
        import base64
        import io
        import re
        from datetime import datetime as _dt
        from pathlib import Path
        from quoteforge.config import OUTPUT_DIR
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as _rl_canvas

        out = io.BytesIO()
        _w, height = letter
        c = _rl_canvas.Canvas(out, pagesize=letter)
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
            b64 = proof_image.split(",", 1)[1]
            if len(b64) <= 24_000_000:                # ~18 MB image; bigger = abuse
                from PIL import Image
                im = Image.open(io.BytesIO(base64.b64decode(b64, validate=True)))
                im = im.convert("RGB")
                im.thumbnail((1200, 1200), Image.LANCZOS)    # downscale to embed
                jpg = io.BytesIO()
                im.save(jpg, "JPEG", quality=85)
                jpg.seek(0)
                img = ImageReader(jpg)
                iw, ih = img.getSize()
                scale = min(1.0, (6.0 * inch) / iw) if iw else 1.0
                dw, dh = iw * scale, ih * scale
                c.drawImage(img, inch, max(0.8 * inch, (y - 0.2 * inch) - dh),
                            dw, dh, preserveAspectRatio=True)
        c.showPage()
        c.save()
        out_dir = Path(OUTPUT_DIR) / "proofs"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", order_id) or "order"
        pdf_path = out_dir / f"{safe_id}_approved.pdf"
        pdf_path.write_bytes(out.getvalue())          # write only after success
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
    order_id, created = _intake_order(email, design_id, contact, money)
    save_design(email, design_json=design_json, design_id=design_id,
                summary=summary, order_id=order_id)
    accept_design(email, design_id)
    if created:                      # only alert on a NEW order, not a duplicate
        _alert_owner(email, summary or "(no summary)", contact)   # confirm of the same basket
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
