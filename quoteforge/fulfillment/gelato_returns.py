"""Gelato-accurate claim & 'return' handling.

Ground truth from gelato.com (Quality & Delivery Guarantee / Help Center):
  * Gelato accepts **no physical returns** and provides **no return address** -
    items are personalized/made to order. There is nothing to ship back.
  * Covered issues (damage, print/production defect, quality, lost-in-transit,
    not caused by the customer's content) are resolved by a **complimentary
    reprint**, NOT a refund-and-return.
  * Claims are filed via the Gelato **Dashboard -> Order Detail -> "Report
    Problem"** flow. **Photos are mandatory** for production issues (the product,
    the packaging, and the shipping label). There is no public self-serve claims
    REST endpoint, so we stage a complete claim package + a deep link rather than
    pretend to POST one.
  * Window: report within **30 days of receiving** the item.
  * Returned-to-sender (wrong address / recipient rejection): the item is
    disposed of and **no refund** is issued. Mitigation per Gelato: place a NEW
    order within 30 days of the estimated delivery date and ask support to refund
    the **product price** on it (you still pay shipping).

Because Gelato never takes the product back, the customer is always told to
**keep/recycle** the original - never to return it.
"""
from datetime import datetime, timedelta

from quoteforge.config import SUPPLIER_CLAIM_DAYS

# Our resolution-engine category -> Gelato "Report Problem" issue type label.
GELATO_ISSUE_TYPES = {
    "damaged_package": "Product damaged in transit",
    "printing_error": "Print / production error",
    "poor_quality": "Print quality issue",
    "lost_package": "Order lost in transit",
    "incomplete_order": "Incomplete order / missing item",
    "wrong_product": "Wrong product received",
}

# Mandatory photo checklist Gelato requires per issue (production issues need the
# product, its packaging, and the shipping label; lost orders use tracking, not
# photos, so the list is empty).
_PHOTO_REQUIREMENTS = {
    "damaged_package": ["product", "packaging", "shipping_label"],
    "printing_error": ["product", "shipping_label"],
    "poor_quality": ["product"],
    "incomplete_order": ["product", "packaging", "shipping_label"],
    "wrong_product": ["product", "shipping_label"],
    "lost_package": [],
}


def gelato_dashboard_url(gelato_order_id: str) -> str:
    """Deep link to the Gelato Dashboard Order Detail page where the owner clicks
    'Report Problem' (no public claims API exists)."""
    return (f"https://dashboard.gelato.com/orders/{gelato_order_id}/"
            if gelato_order_id else "https://dashboard.gelato.com/orders/")


def _no_return_message(order: dict) -> str:
    """The covered-issue reply: replacement on the way, KEEP the original."""
    name = (order.get("recipient_name") or order.get("customer_name") or "there")
    return (f"Hi {name}, I'm so sorry your order didn't arrive in perfect shape! "
            "I've started a free replacement that will be printed and shipped to "
            "you at no charge. There's no need to return the original - please "
            "just keep or recycle it. I'll send tracking as soon as it ships.")


def build_claim_package(order: dict, category: str, photos: list = None) -> dict:
    """Assemble everything Gelato's 'Report Problem' flow needs for one order and
    decide whether it's ready to file.

    Returns the Gelato order reference, mapped issue type, description, the
    mandatory photo checklist (and which are still missing), Gelato coverage and
    window status, a dashboard deep link, the customer reply (keep-the-item), and
    ``ready_to_file`` (covered + in window + all mandatory photos present).
    """
    from quoteforge.etsy.resolution import resolve_issue, claim_window
    from quoteforge.etsy.policy import policy_facts

    res = resolve_issue(category, order)
    cat = res.get("category", category) if res.get("recognized") else category
    pol = policy_facts(cat)
    cw = claim_window(order)
    gelato_ref = order.get("gelato_order_id") or order.get("vendor_order_id") or ""

    covered = bool(pol.get("gelato_covered"))
    required = _PHOTO_REQUIREMENTS.get(cat, ["product"])
    have = {p.strip().lower() for p in (photos or [])}
    missing = [p for p in required if p not in have]
    in_window = cw["within_supplier_window"]
    ready = covered and in_window and not missing

    return {
        "order_id": order.get("order_id"),
        "gelato_order_ref": gelato_ref,
        "category": cat,
        "issue_type": GELATO_ISSUE_TYPES.get(cat, "Other issue"),
        "description": pol.get("recommended", res.get("title", cat)),
        "required_photos": required,
        "missing_photos": missing,
        "gelato_covered": covered,
        "within_gelato_window": in_window,
        "days_since_delivery": cw["days_elapsed"],
        "gelato_window_days": SUPPLIER_CLAIM_DAYS,
        "dashboard_url": gelato_dashboard_url(gelato_ref),
        "submit_method": ("Gelato Dashboard > Order > Report Problem "
                          "(attach photos; no public claims API)"),
        "resolution": "reprint" if covered else "no_gelato_coverage",
        "ready_to_file": ready,
        "customer_message": _no_return_message(order) if covered else res.get("message", ""),
    }


def returned_to_sender_plan(order: dict) -> dict:
    """Plan for an order the carrier is returning to sender (wrong address /
    recipient rejection). Per Gelato: the item is disposed of and **no refund**
    is issued; the mitigation is a new order within 30 days of the estimated
    delivery date plus a product-price refund request (shipping not refunded)."""
    est = order.get("estimated_delivery") or ""
    within = False
    try:
        anchor = datetime.fromisoformat(str(est)[:10]).date()
        within = (datetime.now().date() - anchor) <= timedelta(days=SUPPLIER_CLAIM_DAYS)
    except ValueError:
        within = True   # unknown ETA -> don't pre-empt; treat as actionable

    name = (order.get("recipient_name") or order.get("customer_name") or "there")
    return {
        "order_id": order.get("order_id"),
        "gelato_order_ref": order.get("gelato_order_id") or order.get("vendor_order_id") or "",
        "refund_owed": False,
        "policy": ("Gelato issues no refund for wrong-address or recipient-"
                   "rejection returns; the returned item is disposed of safely."),
        "within_window": within,
        "mitigation": [
            "Confirm the corrected shipping address with the customer.",
            f"Place a NEW Gelato order to the corrected address within "
            f"{SUPPLIER_CLAIM_DAYS} days of the estimated delivery date.",
            "Contact Gelato support referencing the original order to refund the "
            "PRODUCT PRICE on the new order (you pay only the shipping).",
        ],
        "customer_message": (
            f"Hi {name}, your order was returned to us because the carrier "
            "couldn't deliver it to the address on file. I can send a fresh one "
            "to a corrected address right away - could you confirm the full "
            "delivery address? A small reshipping fee applies, and I'll take care "
            "of the rest."),
    }


def record_claim(order_id: str, category: str, status: str = "staged",
                 resolution: str = "") -> None:
    """Persist a Gelato claim's state on the order (for audit + verification):
    status (staged|filed|approved|rejected), category, filed timestamp, and
    Gelato's resolution text once it replies."""
    from quoteforge.db.database import update_order
    fields = {"claim_status": status, "claim_category": category,
              "claim_filed_at": datetime.now().isoformat()}
    if resolution:
        fields["claim_resolution"] = resolution
    update_order(order_id, **fields)


def format_claim_text(pkg: dict) -> str:
    """Render a claim package as an owner-facing checklist + dashboard link."""
    lines = ["=" * 60, f"GELATO CLAIM - {pkg['order_id']} ({pkg['issue_type']})",
             "=" * 60,
             f"  Gelato order ref : {pkg['gelato_order_ref'] or '(missing!)'}",
             f"  Gelato covers    : {'yes (free reprint)' if pkg['gelato_covered'] else 'NO - customer/owner cost'}",
             f"  In 30-day window : {'yes' if pkg['within_gelato_window'] else 'NO'}"
             f"  ({pkg['days_since_delivery']}d since delivery)",
             f"  Photos required  : {', '.join(pkg['required_photos']) or '(tracking, not photos)'}",
             f"  Photos missing   : {', '.join(pkg['missing_photos']) or 'none - complete'}",
             f"  READY TO FILE    : {'YES' if pkg['ready_to_file'] else 'no - resolve the above first'}",
             "",
             f"  File it here -> {pkg['dashboard_url']}",
             f"  {pkg['submit_method']}",
             "",
             "  Reply to send the customer (no return needed):",
             f"  {pkg['customer_message']}",
             "=" * 60]
    return "\n".join(lines)
