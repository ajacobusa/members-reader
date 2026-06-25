"""Customer service request intake + validation + review state machine.

A customer submits a return/refund request (name, order number, email, issue
type, description, photos, delivery date, consent). Instead of being handled
casually in messages, every request is validated against the order record and
moved through a documented review pipeline:

    new -> validating_order -> evidence_review -> supplier_review
        -> approved_reprint | approved_refund | denied | needs_more_info

Internally we validate against: the order id, the customer email ON the order,
the **production-partner / supplier** order id, tracking + delivery date, the
claim window, and the uploaded evidence. (Customer-facing copy never names the
marketplace or the supplier.)
"""
from datetime import datetime

# Customer-facing issue types -> internal resolution category.
ISSUE_TYPES: dict = {
    "Damaged item": "damaged_package",
    "Printing defect": "printing_error",
    "Wrong item received": "wrong_product",
    "Missing item": "incomplete_order",
    "Lost package": "lost_package",
    "Apparel sizing / fit": "wrong_size",   # customer-fault: declined, not reprinted
    "Other": "",
}

# Categories the production partner covers (free reprint / replacement).
_COVERED = {"damaged_package", "printing_error", "poor_quality",
            "wrong_product", "incomplete_order", "lost_package"}

# Required photo evidence per category (product for damage/defect/wrong item;
# packaging additionally for damage). A LOST package genuinely has nothing to
# shoot (it never arrived), but a MISSING-ITEM ("incomplete_order") claim CAN and
# must show what DID arrive - otherwise a zero-photo missing-item claim was being
# recommended straight to supplier_review and would bounce at Gelato (whose own
# auto-file gate, gelato_returns._PHOTO_REQUIREMENTS, requires evidence for it).
_EVIDENCE_RULES: dict = {
    "damaged_package": ["product", "packaging"],
    "printing_error": ["product"],
    "wrong_product": ["product"],
    "incomplete_order": ["product"],
    "lost_package": [],
}

# Review state machine: state -> allowed next states. Terminals have none.
CLAIM_STATES: dict = {
    "new": ["validating_order", "needs_more_info", "denied"],
    "validating_order": ["evidence_review", "needs_more_info", "denied"],
    "evidence_review": ["supplier_review", "needs_more_info", "denied"],
    "supplier_review": ["approved_reprint", "approved_refund", "denied",
                        "needs_more_info"],
    "needs_more_info": ["validating_order", "evidence_review", "supplier_review",
                        "denied"],
    "approved_reprint": [],
    "approved_refund": [],
    "denied": [],
}

CUSTOMER_ACK = (
    "Thank you. Your request has been received and will be reviewed. Because all "
    "items are custom-made, requests are reviewed individually. We may contact "
    "you for additional information.")


def advance_claim(current: str, target: str) -> dict:
    """Validate a review state transition. Returns {ok, reason}."""
    allowed = CLAIM_STATES.get(current)
    if allowed is None:
        return {"ok": False, "reason": f"unknown state '{current}'"}
    if target not in allowed:
        return {"ok": False,
                "reason": f"'{current}' cannot move to '{target}' "
                          f"(allowed: {', '.join(allowed) or 'none - terminal'})"}
    return {"ok": True, "reason": ""}


def _find_order(order_number: str):
    """Look up the order by the customer-entered order number (marketplace
    receipt id first, then internal id)."""
    from quoteforge.db.database import get_order_by_etsy_id, get_order
    return (get_order_by_etsy_id(order_number) or get_order(order_number)
            if order_number else None)


def validate_claim_request(request: dict) -> dict:
    """Validate a service request against the order record and recommend the
    next review state. Pure - persists nothing (see intake_claim).

    `request` keys: order_number, name, email, issue_type, description, photos
    (list of labels), delivery_date (optional), preferred_resolution (optional).
    """
    from quoteforge.etsy.resolution import claim_window

    category = ISSUE_TYPES.get(request.get("issue_type", ""), "")
    order = _find_order((request.get("order_number") or "").strip())
    req_email = (request.get("email") or "").strip().lower()
    photos = {str(p).strip().lower() for p in (request.get("photos") or [])}

    order_found = order is not None
    email_matches = bool(order) and req_email == (order.get("customer_email") or "").strip().lower()
    supplier_ref = (order.get("gelato_order_id") or order.get("vendor_order_id") or "") if order else ""
    cw = claim_window(order) if order else {"within_supplier_window": False,
                                            "days_elapsed": None,
                                            "eligibility": "unknown"}
    # The customer-facing claim window is 7 days from delivery (the storefront
    # promise). Past 7 days a claim is NOT auto-accepted; what happens next
    # depends on supplier coverage:
    #   * <= 7 days (or admin override)   -> normal review flow
    #   * 8 days .. supplier window (30d) -> held for ADMIN review (the supplier
    #     still reprints for free, so never auto-deny a covered claim)
    #   * past the supplier window        -> denied (no coverage; admin can override)
    admin_override = bool(request.get("admin_override"))
    eligibility = cw.get("eligibility", "unknown")
    within_supplier = bool(order) and cw.get("within_supplier_window", True)
    past_window = eligibility in ("manual_review", "management_approval")
    within_window = bool(order) and (admin_override or not past_window)
    requires_admin_review = bool(order) and past_window and within_supplier and not admin_override
    required = _EVIDENCE_RULES.get(category, ["product"])
    missing_evidence = [p for p in required if p not in photos]
    evidence_complete = not missing_evidence

    checks = {
        "order_found": order_found,
        "email_matches": email_matches,
        "supplier_order_id": bool(supplier_ref),
        "within_window": within_window,
        "admin_override": admin_override,
        "requires_admin_review": requires_admin_review,
        "evidence_complete": evidence_complete,
        "tracking_status": (order.get("status") if order else ""),
        "delivery_date": (order.get("delivered_at") if order else "") or request.get("delivery_date", ""),
    }

    # Recommended next state from the checks (final approve/deny stays human).
    if not order_found or not email_matches or not category:
        status = "needs_more_info"
    elif within_window:
        # In the 7-day window (or admin-overridden): normal review flow.
        if not evidence_complete:
            status = "needs_more_info"
        elif category in _COVERED:
            status = "supplier_review"
        else:
            status = "needs_more_info"
    elif within_supplier:
        # Past 7 days but the supplier still covers a free reprint: hold for an
        # admin decision rather than auto-denying a legitimate covered claim.
        status = "needs_more_info"
    else:
        # Past the supplier window - no coverage. Denied unless an admin overrode.
        status = "denied"

    return {
        "order_id": order.get("order_id") if order else "",
        "category": category,
        "issue_type": request.get("issue_type", ""),
        "supplier_order_ref": supplier_ref,
        "gelato_covered": category in _COVERED,
        "checks": checks,
        "missing_evidence": missing_evidence,
        "days_since_delivery": cw.get("days_elapsed"),
        "window_eligibility": eligibility,
        "admin_override": admin_override,
        "requires_admin_review": requires_admin_review,
        "recommended_status": status,
        "customer_ack": CUSTOMER_ACK,
    }


def intake_claim(request: dict) -> dict:
    """Validate + DOCUMENT a service request: runs validate_claim_request, then
    persists the recommended status, category, and any photo evidence on the
    order (when matched). Returns the validation result."""
    result = validate_claim_request(request)
    oid = result["order_id"]
    if oid:
        from quoteforge.fulfillment.gelato_returns import record_claim, record_claim_photos
        from quoteforge.db.database import update_order
        record_claim(oid, result["category"] or "other", result["recommended_status"])
        # Distinguish a held-for-admin claim (past 7d, supplier still covers) from
        # a missing-evidence hold - both recommend "needs_more_info".
        update_order(oid, claim_needs_admin="1" if result.get("requires_admin_review") else "")
        if request.get("photos"):
            record_claim_photos(oid, request["photos"])
    return result


def format_request_text(result: dict) -> str:
    """Render a validated service request for the owner (checklist + status)."""
    c = result["checks"]
    yn = lambda b: "✓" if b else "✗"
    return "\n".join([
        "=" * 60, f"SERVICE REQUEST - {result['issue_type']} "
                  f"(order {result['order_id'] or '?'})", "=" * 60,
        f"  {yn(c['order_found'])} order found",
        f"  {yn(c['email_matches'])} email matches order",
        f"  {yn(c['supplier_order_id'])} supplier order id ({result['supplier_order_ref'] or 'missing'})",
        f"  {yn(c['within_window'])} within claim window ({result['days_since_delivery']}d since delivery)",
        f"  {yn(c['evidence_complete'])} evidence complete"
        + (f" (missing: {', '.join(result['missing_evidence'])})" if result["missing_evidence"] else ""),
        f"  tracking: {c['tracking_status']}   delivered: {c['delivery_date'] or 'n/a'}",
        "", f"  RECOMMENDED STATUS -> {result['recommended_status']}",
        f"  Production-partner / supplier covers: {'yes' if result['gelato_covered'] else 'no'}",
        "=" * 60])
