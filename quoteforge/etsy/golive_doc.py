"""Go-Live checklist PDF - the exact ordered steps + commands to launch."""
from __future__ import annotations

GREEN = "#103D2E"

DONE = [
    "Storefront + 20 launch listings (SEO titles + 13 tags + descriptions).",
    "Full order->delivery automation (intake, AI quote, QC, proof, fulfillment, "
    "tracking, delight).",
    "Ask Ange AI assistant (free on-page; optional live Claude endpoint).",
    "Email capture: Etsy announcement, QR insert, Linktree, website signup.",
    "Pinterest: pin packs + pins.csv (5-10 pins/product, gift-guide & seasonal).",
    "Analytics ready: Etsy Shop Stats (enable in Etsy), Google Analytics + "
    "Microsoft Clarity (set IDs).",
    "Reporting: daily ledger, Friday review, monthly executive packet (all costs), "
    "AI ops review - archived in the cost folder + emailed.",
    "Safety: 60% margin floor, QC-before-proof, human-approved refunds, backups.",
]

STEPS = [
    ("1. Approve the physical sample (THE gate)",
     "Place one real Gelato order from your design, confirm print + color "
     "quality in hand. Nothing else goes live until this passes."),
    ("2. Add real keys to .env",
     "ANTHROPIC_API_KEY, GELATO_API_KEY, ETSY_API_KEY + ETSY_OAUTH_TOKEN/"
     "REFRESH_TOKEN, GMAIL_ADDRESS + app password. (See .env.example.)"),
    ("3. Verify",
     "python -m quoteforge.admin verify-keys   then   "
     "python -m quoteforge.admin preflight"),
    ("4. Go live",
     "Set TEST_MODE=false in .env (only after the sample is approved)."),
    ("5. Publish the Etsy listings",
     "python -m quoteforge.admin publish-listings --live   (creates drafts + "
     "uploads images) -> review and hit Publish on each in Etsy. Apply the "
     "variation matrix from etsy_inventory.csv (Material x Size x Frame)."),
    ("6. Confirm Etsy shop settings",
     "Production partner = Gelato; shipping profile set; return/cancel policy; "
     "payments + currency (USD); shop icon/banner; About + announcement."),
    ("7. Turn on automation",
     "python -m quoteforge.admin install-schedule   (run as Administrator) - "
     "registers all 26 scheduled jobs. (Or host per docs/DEPLOY.md.)"),
    ("8. Marketing switches (optional, free)",
     "Set SIGNUP_URL (mailing list), GA_MEASUREMENT_ID + CLARITY_PROJECT_ID, "
     "FEEDBACK_FORM_URL. Run: email-capture, pinterest. Apply to affiliate "
     "programs: python -m quoteforge.admin affiliates."),
    ("9. (Optional) brand domain",
     "Buy joffiels.com (GoDaddy ~$15/yr) -> GitHub Pages (see docs/"
     "DOMAIN_SETUP.md). The site funnels to Etsy; Etsy stays the checkout."),
]

CHEAT = [
    ("Daily ops read", "briefing"),
    ("Pull new Etsy orders", "poll-etsy"),
    ("Sync tracking -> buyers", "track-orders"),
    ("Buyer approved -> print", "customer-approved ID"),
    ("Resolve an issue", "autopilot \"<issue>\" ID"),
    ("Cost & profit P&L", "ledger month"),
    ("Friday review email", "weekly-review email"),
    ("Monthly exec packet", "monthly-review email"),
    ("Executive report", "exec-report all"),
    ("Workflow PDF", "workflow-pdf"),
    ("Ask Ange a question", "ask \"...\""),
    ("Full backup + push", "backup-all"),
]


def build_golive_pdf(out_path=None):
    from pathlib import Path
    from datetime import date
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, ListFlowable, ListItem)
    from quoteforge.config import OUTPUT_DIR, SHOP_NAME

    out = Path(out_path) if out_path else (OUTPUT_DIR / "Joffiels_Go_Live_Checklist.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=colors.HexColor(GREEN))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor(GREEN),
                        spaceBefore=12)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=10, leading=14)
    mono = ParagraphStyle("mono", parent=body, fontName="Courier", fontSize=8.5,
                          textColor=colors.HexColor("#333333"))

    doc = SimpleDocTemplate(str(out), pagesize=letter, leftMargin=0.7 * inch,
                            rightMargin=0.7 * inch, topMargin=0.7 * inch,
                            bottomMargin=0.6 * inch)
    el = [Paragraph(f"{SHOP_NAME} - Go-Live Checklist", h1),
          Paragraph(date.today().isoformat(), body), Spacer(1, 8)]

    el.append(Paragraph("Already built &amp; confirmed", h2))
    el.append(ListFlowable([ListItem(Paragraph(i, body)) for i in DONE],
                           bulletType="bullet", start="square"))

    el.append(Paragraph("Launch steps (in order)", h2))
    for title, detail in STEPS:
        el.append(Paragraph("<b>" + title + "</b>", body))
        el.append(Paragraph(detail, body))
        el.append(Spacer(1, 4))

    el.append(Paragraph("Command cheat-sheet", h2))
    rows = [[Paragraph("<b>Do this</b>", body),
             Paragraph("<b>python -m quoteforge.admin ...</b>", body)]]
    for lbl, cmd in CHEAT:
        rows.append([Paragraph(lbl, body), Paragraph(cmd, mono)])
    t = Table(rows, colWidths=[2.4 * inch, 4.4 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GREEN)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8CDB6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F4F1EA")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el.append(t)
    el.append(Spacer(1, 8))
    el.append(Paragraph("The one true gate is Step 1. Everything else is ready.",
                        body))
    doc.build(el)
    return out
