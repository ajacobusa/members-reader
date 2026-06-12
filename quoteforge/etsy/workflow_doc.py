"""End-to-end workflow PDF - Etsy order entry -> delivery, every step.

Generates a styled PDF covering the customer experience, behind-the-scenes
automation, AI touch-points, image/quality handling, payment, fulfillment,
delivery, and back-office - plus an auditor's notes/gaps section.
"""
from __future__ import annotations

GREEN = "#103D2E"
GOLD = "#C9A84C"

# (stage, customer experience, behind the scenes, AI?, status)
STAGES = [
    ("1. Discover",
     "Finds Joffiels on Etsy search / Pinterest / Google, or the brand site.",
     "SEO'd titles+13 tags, seasonal SEO refresh, Pinterest auto-pins, GitHub "
     "Pages brand site, order-by urgency banner.",
     "AI writes SEO + Pinterest copy; seasonal demand timing.", "LIVE"),
    ("2. Browse & get advice",
     "Browses pieces, asks questions, sees what to buy for the occasion.",
     "Shop-by-occasion nav, verified reviews, happiness guarantee, FAQ.",
     "ASK ANGE bot answers frames/sizes/shipping/returns and ADVISES what to "
     "buy; defers refunds/personal to a human.", "LIVE"),
    ("3. Select & customize",
     "Picks Material, Size, Quantity (mix sizes), frame style; previews colors, "
     "font and wording live; builds a multi-item order.",
     "Variation model (Material x Size x Frame), 60% price floor, bundle "
     "discounts, live canvas preview, character counter.",
     "Live final-product render reacts to every choice.", "LIVE"),
    ("4. Upload own photo (optional)",
     "Uploads a personal photo; told instantly if it's too low-res to print "
     "sharply and asked for a better one.",
     "Client-side format+resolution check (JPG/PNG/PDF/TIFF, 150 DPI min for the "
     "chosen size); backend photo_check re-verifies on the real order.",
     "Auto-evaluates quality; auto-emails a polite 'please resend' if poor.",
     "LIVE"),
    ("5. Add a gift",
     "Adds a gift e-card + a free personal note; recipient gets a surprise "
     "announcement.",
     "Gift e-card line item; recipient email captured (consent=pending).",
     "AI writes the free personal note from the buyer's words.", "LIVE"),
    ("6. Checkout & pay",
     "Adds to cart, adjusts quantities, pays securely.",
     "ETSY handles cart + checkout + payment (Etsy Payments) + buyer protection. "
     "Nothing to build; multi-item supported.",
     "-", "ETSY"),
    ("7. Order intake",
     "Gets Etsy order confirmation.",
     "poll-etsy imports every 10 min (no Make/Zapier); per-customer folder "
     "created; buyer auto-enrolled to list; subscription orders activated.",
     "-", "LIVE"),
    ("8. Design",
     "(waits) - their personalized piece is created.",
     "Quote/message generated; artwork rendered; buyer photo used if provided.",
     "Claude writes the personalized, copyright-safe message.", "LIVE"),
    ("9. Final QC (before proof)",
     "Nothing yet - quality is checked first.",
     "Preflight (DPI/size/aspect/colour) + optional Claude VISION review; fail = "
     "hold + flag, proof NOT sent.",
     "AI vision checks for cut-off text/typos/blur.", "LIVE"),
    ("10. Proof & approval",
     "Receives a FREE digital proof; nothing prints until they approve.",
     "Proof prepared; printing blocked until approval recorded (hard gate).",
     "-", "LIVE"),
    ("11. Fulfillment",
     "(waits) - piece is produced.",
     "Vendor-routed: Gelato (API) / Printful / Printify / digital / manual; "
     "live price+availability sync; 60% margin protected.",
     "-", "LIVE"),
    ("12. Shipping & tracking",
     "Gets a tracking number and can follow the package.",
     "Every 6h: Gelato tracking -> order marked shipped/delivered + tracking "
     "pushed to the Etsy buyer (createReceiptShipment).",
     "-", "LIVE"),
    ("13. Delivery & delight",
     "Receives the gift; ~6 days later a warm review + referral ask.",
     "Delight loop (idempotent) fires after delivery; referral + thank-you "
     "coupon.",
     "-", "LIVE"),
    ("14. Retention / LTV",
     "Occasion reminders, win-backs, membership renewals, gift-recipient "
     "becomes a future customer.",
     "Retention engine, subscriptions + AI renewal reminders, gift-recipient "
     "capture.",
     "AI writes renewal + win-back emails.", "LIVE"),
    ("15. Back-office (you)",
     "Owner gets daily/Friday/monthly reports automatically.",
     "Daily ledger, Friday business review (+ledger+reconciliation+trend), "
     "monthly exec packet, AI ops review, backups, healthcheck.",
     "AI summarizes performance + recommends actions.", "LIVE"),
]

MONEY_SAFETY = [
    "Payment is taken by Etsy (PCI-compliant) - we never touch card data.",
    "60% net margin floor enforced on every variation + bundle.",
    "Refunds/returns ALWAYS require human approval (hard rule).",
    "No API keys exposed on the static site; secrets stay in .env / host vault.",
    "Nightly encrypted-off-machine backup (GitHub push + optional Drive).",
]

IMAGE_QUALITY = [
    "On upload (site): instant client-side check - format (JPG/PNG/PDF/TIFF) + "
    "resolution vs the chosen size (>=150 DPI), with an immediate re-upload "
    "prompt if too small.",
    "On the real order (backend): photo_check recomputes effective DPI vs the "
    "product's print spec; below threshold -> order held.",
    "Auto-reply: a polite, specific 'please send the original full-size photo' "
    "email is sent automatically (owner BCC'd).",
    "Final product: preflight (DPI/size/aspect/colour mode) + optional Claude "
    "vision QC run BEFORE the proof - nothing reaches the customer until it "
    "passes.",
    "Gelato print files: 300 DPI target; the catalog stores exact pixel specs "
    "per size.",
]

GAPS = [
    "Go-live gate: approve the physical Gelato sample, set real keys, flip "
    "TEST_MODE=false.",
    "Host the server (Render ~$7/mo) for live Ask Ange answers + inbound "
    "webhooks (today: scheduled poll works on your PC).",
    "Etsy variation auto-upload needs OAuth write scope (CSV is ready now).",
    "Reviews populate post-launch via the delight loop (no fabricated reviews).",
    "At volume (>30 orders/day): SQLite -> Postgres + a job queue.",
]


def build_workflow_pdf(out_path=None):
    """Build the end-to-end workflow PDF and return its path."""
    from pathlib import Path
    from datetime import date
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, ListFlowable, ListItem)
    from quoteforge.config import OUTPUT_DIR, SHOP_NAME

    out = Path(out_path) if out_path else (OUTPUT_DIR / "Joffiels_End_to_End_Workflow.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=colors.HexColor(GREEN))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor(GREEN),
                        spaceBefore=14)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13)
    cell = ParagraphStyle("cell", parent=body, fontSize=8.2, leading=10.5)
    cellb = ParagraphStyle("cellb", parent=cell, textColor=colors.white)

    doc = SimpleDocTemplate(str(out), pagesize=letter,
                            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.6 * inch)
    el = []
    el.append(Paragraph(f"{SHOP_NAME} - End-to-End Workflow", h1))
    el.append(Paragraph(f"Etsy order entry &rarr; delivery &middot; customer "
                        f"experience, AI, fulfillment, payment &middot; "
                        f"{date.today().isoformat()}", body))
    el.append(Spacer(1, 10))
    el.append(Paragraph(
        "How the business runs end to end: what the customer sees, what happens "
        "automatically behind the scenes, where AI helps, and how quality, "
        "payment and delivery are handled. Etsy is the cash register; everything "
        "else is automated.", body))

    el.append(Paragraph("The 15-step journey", h2))
    head = [Paragraph("Stage", cellb), Paragraph("Customer experience", cellb),
            Paragraph("Behind the scenes", cellb), Paragraph("AI", cellb),
            Paragraph("Status", cellb)]
    rows = [head]
    for st in STAGES:
        rows.append([Paragraph(st[0], cell), Paragraph(st[1], cell),
                     Paragraph(st[2], cell), Paragraph(st[3], cell),
                     Paragraph(st[4], cell)])
    tbl = Table(rows, colWidths=[0.95 * inch, 1.9 * inch, 2.5 * inch,
                                 1.55 * inch, 0.55 * inch], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8CDB6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F4F1EA")]),
    ]))
    el.append(tbl)

    def _bullets(title, items):
        """Append a heading plus a bulleted list to the document."""
        el.append(Paragraph(title, h2))
        el.append(ListFlowable(
            [ListItem(Paragraph(i, body), leftIndent=10) for i in items],
            bulletType="bullet", start="square"))

    _bullets("Image &amp; upload quality (auto-checked, AI-assisted)", IMAGE_QUALITY)
    _bullets("Payment &amp; money safety", MONEY_SAFETY)
    _bullets("Auditor notes &amp; go-live items", GAPS)

    el.append(Paragraph("Bottom line", h2))
    el.append(Paragraph(
        "From discovery to delivery the flow is complete and AI-aware: AI advises "
        "the buyer (Ask Ange), personalizes the piece, checks photo + final-"
        "product quality before the customer ever sees a proof, routes "
        "fulfillment, syncs tracking, and runs retention + reporting - while Etsy "
        "handles payment and the 60% margin floor + human-approved refunds keep "
        "it safe.", body))

    doc.build(el)
    return out
