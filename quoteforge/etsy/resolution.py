"""Customer-issue resolution engine for personalized Etsy + Gelato orders.

Encodes the standard POD policy: personalized items are final sale, but genuine
defects/damage/loss get a free replacement via Gelato's guarantee. Given an issue
category it returns an automatic decision (who is at fault, what we do, who pays,
the workflow steps, and a ready-to-send customer message), so resolutions are
consistent and defensible.

Fault → outcome:
  customer error  -> no refund (optional paid reprint)
  production error -> free replacement
  shipping damage  -> Gelato claim -> reprint
  lost package     -> investigate tracking -> replacement
"""
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Resolution:
    """One issue category's decision: fault, outcome, workflow, and reply text."""
    category: str
    title: str
    fault: str            # "customer" | "production" | "shipping" | "none"
    decision: str         # short outcome, e.g. "No refund", "Free replacement"
    gelato_covered: bool  # does Gelato's guarantee pay for it?
    customer_pays: bool   # does the buyer pay for any reprint/shipping?
    workflow: list[str] = field(default_factory=list)
    message: str = ""     # ready-to-send reply to the customer


# Ordered to match the standard 8 cases (+ cancellation).
ISSUE_CASES: dict[str, Resolution] = {
    "changed_mind": Resolution(
        "changed_mind", "Customer changed their mind", "customer",
        "No refund, no return", False, False,
        ["Confirm item is personalized (final sale)",
         "Politely decline refund, cite personalization policy"],
        "Thank you for reaching out. Because this piece was personalized and "
        "made to order just for you, it's final sale and can't be returned or "
        "refunded. I'm always happy to help if anything actually arrived damaged "
        "or defective - just send a photo."),
    "wrong_personalization": Resolution(
        "wrong_personalization", "Customer entered the wrong personalization",
        "customer", "No refund; offer discounted reprint", False, True,
        ["Confirm the order was produced exactly as the customer typed",
         "Offer a discounted reprint with the corrected details"],
        "Thanks for letting me know! I checked your order and the print was made "
        "exactly as the details were entered at checkout, so I'm not able to "
        "offer a free replacement. I'd love to make it right though - I can do a "
        "discounted reprint with the correct spelling. Want me to set that up?"),
    "approved_then_changed_mind": Resolution(
        "approved_then_changed_mind", "Customer approved the proof, then changed mind",
        "customer", "No refund, no replacement", False, False,
        ["Pull the proof-approval record (timestamp on file)",
         "Politely decline, referencing their approval"],
        "Thank you for your message. Our records show the proof was reviewed and "
        "approved before printing, and the item was produced to match that "
        "approved design. Because it's a personalized, made-to-order piece, I'm "
        "unable to offer a refund or replacement - but I truly appreciate your "
        "order and am here for anything else."),
    "damaged_package": Resolution(
        "damaged_package", "Package/product arrived damaged", "shipping",
        "Free replacement", True, False,
        ["Ask customer for photos of the damage + packaging",
         "Submit a damage claim to Gelato with the photos",
         "Gelato investigates and reprints - no charge to the customer"],
        "Oh no, I'm so sorry your order arrived damaged! Could you send me a "
        "couple of photos of the item and the packaging? As soon as I have those "
        "I'll get a free replacement sent out right away - no need to return the "
        "damaged one."),
    "printing_error": Resolution(
        "printing_error", "Printing/production error (our or Gelato's fault)",
        "production", "Free replacement", True, False,
        ["Compare the order details to what was produced",
         "If it differs from the approved order, submit to Gelato",
         "Reprint at no charge to the customer"],
        "I'm sorry about that - it looks like the print didn't come out the way "
        "it should have. That's on us, and I'll get a corrected replacement sent "
        "to you free of charge. Thank you for your patience!"),
    "poor_quality": Resolution(
        "poor_quality", "Poor print quality (fading, blur, cropping)",
        "production", "Free replacement", True, False,
        ["Ask for photos showing the quality issue",
         "Submit evidence to Gelato as a quality claim",
         "Reprint at no charge"],
        "Thanks for flagging this, and I'm sorry the print quality isn't up to "
        "standard. If you can send a photo showing the issue, I'll submit it and "
        "get a free replacement on the way to you."),
    "lost_package": Resolution(
        "lost_package", "Package lost in transit", "shipping",
        "Replacement after investigation", True, False,
        ["Check the tracking status",
         "If lost/stalled past the window, file a claim with Gelato",
         "Send a replacement once confirmed"],
        "I'm sorry your order hasn't arrived. Let me look into the tracking right "
        "away - if it's confirmed lost in transit, I'll arrange a replacement at "
        "no cost to you. I'll follow up shortly with an update."),
    "wrong_address": Resolution(
        "wrong_address", "Wrong address entered by customer", "customer",
        "No refund; customer pays reprint + shipping", False, True,
        ["Confirm the address used matches what the customer entered",
         "Explain Gelato doesn't cover customer address errors",
         "Offer a paid reprint to the correct address"],
        "Thanks for reaching out. The order shipped to the address entered at "
        "checkout, and unfortunately address mistakes aren't covered by our print "
        "partner. I can absolutely send a new one to the correct address - it "
        "would be the reprint plus shipping. Would you like me to arrange that?"),
    "cancellation": Resolution(
        "cancellation", "Cancellation request", "none",
        "Accepted only before production begins", False, False,
        ["Check whether production has started (~2-4h window)",
         "If not started: cancel and full refund",
         "If already in production: decline (personalized, final sale)"],
        "Thanks for reaching out. If your order hasn't gone into production yet "
        "(usually within a few hours of ordering) I can cancel it for a full "
        "refund. If it's already being made, it's personalized and can't be "
        "cancelled - let me check and I'll let you know right away."),
}

# Friendly aliases so callers can pass natural language.
_ALIASES = {
    "changed my mind": "changed_mind", "dont want": "changed_mind",
    "don't want": "changed_mind", "no longer want": "changed_mind",
    "wrong name": "wrong_personalization", "typo": "wrong_personalization",
    "misspelled": "wrong_personalization", "mistyped": "wrong_personalization",
    "wrong spelling": "wrong_personalization", "spelled wrong": "wrong_personalization",
    "approved": "approved_then_changed_mind",
    "damaged": "damaged_package", "broken": "damaged_package",
    "torn": "damaged_package", "ripped": "damaged_package",
    "bent": "damaged_package", "crushed": "damaged_package",
    "dented": "damaged_package", "cracked": "damaged_package",
    "arrived damaged": "damaged_package",
    "defect": "printing_error", "misprint": "printing_error",
    "printing error": "printing_error", "printed wrong": "printing_error",
    "wrong color": "poor_quality", "quality": "poor_quality",
    "blurry": "poor_quality", "faded": "poor_quality", "pixelated": "poor_quality",
    "cropped": "poor_quality",
    "lost": "lost_package", "never arrived": "lost_package",
    "didn't arrive": "lost_package", "hasn't arrived": "lost_package",
    "missing package": "lost_package",
    "wrong address": "wrong_address", "address": "wrong_address",
    "cancel": "cancellation", "cancellation": "cancellation",
}


def _to_date(value) -> date | None:
    """Parse an ISO date/datetime string (or pass through date/datetime) to a
    date, tolerating trailing time and a 'Z' suffix; None when unparseable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip().replace("Z", "")
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        try:
            return datetime.fromisoformat(s[:10]).date()
        except ValueError:
            return None


def claim_window(order: dict | None, report_date=None) -> dict:
    """Evaluate a claim's REPORTING DEADLINE against the delivery anchor.

    The clock starts at the carrier-confirmed delivery date when we have one
    (``delivery_confirmed`` truthy + ``delivered_at``); otherwise at the
    estimated-delivery date (assumed-delivered orders with no carrier timestamp),
    falling back to a bare ``delivered_at``. ``report_date`` defaults to today
    and should be the customer's FIRST contact, not when evidence arrives.

    Tiers (calendar days elapsed): 0..REPORT -> ``eligible``; REPORT+1..FLAG ->
    ``manual_review``; > FLAG -> ``management_approval``. ``within_supplier_window``
    is False once past the partner's filing window (no partner reimbursement).
    With no usable date the result is ``unknown`` and is not blocked.
    """
    from quoteforge.config import (CLAIM_REPORT_DAYS, CLAIM_FLAG_DAYS,
                                   SUPPLIER_CLAIM_DAYS)
    if order and order.get("delivery_confirmed") and order.get("delivered_at"):
        anchor, anchor_type = _to_date(order.get("delivered_at")), "carrier_confirmed"
    elif order and order.get("estimated_delivery"):
        anchor, anchor_type = _to_date(order.get("estimated_delivery")), "estimated_delivery"
    elif order and order.get("delivered_at"):
        anchor, anchor_type = _to_date(order.get("delivered_at")), "assumed_delivery"
    else:
        anchor, anchor_type = None, "none"

    if anchor is None:
        return {"anchor_type": "none", "anchor_date": "", "days_elapsed": None,
                "eligibility": "unknown", "within_supplier_window": True,
                "note": "No delivery date on record - route to manual review."}

    today = _to_date(report_date) or datetime.now().date()
    days = (today - anchor).days
    if days <= CLAIM_REPORT_DAYS:
        eligibility = "eligible"
    elif days <= CLAIM_FLAG_DAYS:
        eligibility = "manual_review"
    else:
        eligibility = "management_approval"
    within_supplier = days <= SUPPLIER_CLAIM_DAYS
    note = {
        "eligible": f"Reported within {CLAIM_REPORT_DAYS} days - accept into review queue.",
        "manual_review": "Past the standard window - allow but flag for manual review.",
        "management_approval": "Well past the window - requires management approval.",
    }[eligibility]
    if not within_supplier:
        note += (f" Past the {SUPPLIER_CLAIM_DAYS}-day partner filing window - "
                 "the production partner will not reimburse (goodwill/at-cost).")
    return {"anchor_type": anchor_type, "anchor_date": anchor.isoformat(),
            "days_elapsed": days, "eligibility": eligibility,
            "within_supplier_window": within_supplier, "note": note}


def resolve_issue(category: str, order: dict | None = None) -> dict:
    """Return the automatic decision for an issue category.

    `category` may be a case key or a natural-language phrase. If an `order` is
    given and it has a proof-approval record, that evidence is attached to
    strengthen a customer-fault denial.
    """
    key = (category or "").strip().lower().replace(" ", "_")
    if key not in ISSUE_CASES:
        # try alias match on the raw phrase
        raw = (category or "").strip().lower()
        key = next((v for a, v in _ALIASES.items() if a in raw), "")
    if key not in ISSUE_CASES:
        return {"recognized": False, "category": category,
                "options": list(ISSUE_CASES.keys())}

    r = ISSUE_CASES[key]
    out = {
        "recognized": True,
        "category": r.category,
        "title": r.title,
        "fault": r.fault,
        "decision": r.decision,
        "gelato_covered": r.gelato_covered,
        "customer_pays": r.customer_pays,
        "workflow": list(r.workflow),
        "message": r.message,
        "evidence": "",
        "claim_window": claim_window(order) if order else None,
    }
    if order and r.fault == "customer" and order.get("proof_approved"):
        out["evidence"] = (
            f"Proof approved by customer on "
            f"{order.get('proof_approved_at', 'record on file')} - denial is "
            f"well-supported.")
    return out


def format_resolution_text(res: dict) -> str:
    """Render a resolution decision as printable console text."""
    if not res["recognized"]:
        return ("Unrecognized issue. Choose one of:\n  "
                + "\n  ".join(res["options"]))
    lines = ["=" * 56, f"RESOLUTION - {res['title']}", "=" * 56,
             f"Fault         : {res['fault']}",
             f"Decision      : {res['decision']}",
             f"Gelato covers : {'yes' if res['gelato_covered'] else 'no'}",
             f"Customer pays : {'yes' if res['customer_pays'] else 'no'}"]
    cw = res.get("claim_window")
    if cw and cw["eligibility"] != "unknown":
        lines.append(f"Claim window  : {cw['eligibility']} "
                     f"({cw['days_elapsed']}d since {cw['anchor_type']}"
                     + ("" if cw["within_supplier_window"]
                        else "; PAST partner filing window") + ")")
    elif cw:
        lines.append("Claim window  : unknown (no delivery date on record)")
    if res["evidence"]:
        lines.append(f"Evidence      : {res['evidence']}")
    lines.append("\nWorkflow:")
    for i, step in enumerate(res["workflow"], 1):
        lines.append(f"  {i}. {step}")
    lines.append("\nMessage to send the customer:\n")
    lines.append(res["message"])
    lines.append("=" * 56)
    return "\n".join(lines)
