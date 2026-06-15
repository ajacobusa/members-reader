"""End-to-end order compliance monitor.

Walks every order and validates it against the Order Approval / Production /
Cancellation / Return & Refund policy and the fulfillment state machine:

  * Production only begins AFTER the customer approves (design locked):
    an order in production/shipped/delivered must carry proof_approved.
  * An order at production stage must have been submitted to the vendor.
  * Cancellation after production began is review-required (orders move quickly
    into production and generally cannot be canceled afterward).
  * Delivery is verified by carrier confirmation; a delivered-but-disputed order
    (Etsy case/refund/complaint) is NOT a clean completion.
  * Returns/refunds are not automatic for custom items - each claim is reviewed
    individually per the resolution policy (qualifying: damaged / defect /
    printing error / wrong fulfillment / lost; non-qualifying: change of mind,
    customer-approved typos/design/photo quality, normal print variation).

Runs on a schedule; emails the owner when there are violations or items needing
individual review. Read-only - it flags, it does not mutate orders.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Stages at or past production (design is locked, manufacturing under way).
PRODUCTION_PLUS = ("in_production", "shipped", "delivered")


def order_stage(order: dict) -> str:
    """The order's current lifecycle stage (its status), defaulting to received."""
    return (order.get("status") or "received").lower()


def _has_vendor(order: dict) -> bool:
    """Whether the order was actually submitted to a print vendor."""
    return bool(order.get("vendor_order_id") or order.get("gelato_order_id"))


def audit_order(order: dict) -> dict:
    """Validate one order against the policy + state machine. Returns
    {order_id, status, issues (hard violations), review (needs a human),
    compliant}."""
    status = order_stage(order)
    issues: list[str] = []
    review: list[str] = []

    # Approval gate: production must not begin before the customer locks the
    # design (proof approved / auto-approved).
    if status in PRODUCTION_PLUS and not order.get("proof_approved"):
        issues.append("in production/shipped without recorded customer approval "
                      "- the design-lock/approval gate was bypassed")
    # Must have been submitted to the vendor to be in production.
    if status in PRODUCTION_PLUS and not _has_vendor(order):
        issues.append("at a production stage but no vendor order id "
                      "- never actually submitted to the print partner")
    # Cancellation timing.
    if status == "cancelled" and _has_vendor(order):
        review.append("cancelled AFTER production began - review individually "
                      "(custom orders generally cannot be canceled once in production)")
    # Delivery verification.
    if status == "delivered":
        if order.get("delivery_disputed"):
            review.append("delivered but DISPUTED (Etsy case / refund / complaint) "
                          "- not a clean completion; resolve before closing")
        elif not (order.get("delivery_confirmed")
                  or order.get("manual_delivery_confirmed")
                  or order.get("delivered_at")):
            issues.append("marked delivered without carrier confirmation "
                          "or a delivered_at timestamp")
    # Refund must have followed the individual-review claim process.
    if status == "refunded":
        review.append("refunded - confirm it went through the individual claim "
                      "review (custom items have no automatic refund)")

    # Margin floor: a real order priced/costed below the floor (custom or
    # discounted price, live cost spike, heavy upcharge) leaks margin silently.
    # The catalog audit only covers the static price book; this catches the
    # economics of the ACTUAL order. Flag for review, don't block fulfilment.
    sale_price, gelato_cost = order.get("sale_price"), order.get("gelato_cost")
    # Check whenever there is a real product cost - including a $0 sale price
    # (giveaway / 100%-off coupon), which is the WORST margin case and must not
    # be skipped by a truthiness test. A 0/None cost is a pre-pricing placeholder
    # with no economics to audit.
    if sale_price is not None and gelato_cost:
        try:
            from quoteforge.etsy.margin_guard import margin_check
            m = margin_check(float(sale_price), float(gelato_cost))
            if not m["ok"]:
                review.append(
                    f"margin {m['margin_pct']:.1f}% is below the "
                    f"{m['floor_pct']:.0f}% floor (sale ${float(sale_price):.2f} / "
                    f"cost ${float(gelato_cost):.2f}) - review pricing")
        except (TypeError, ValueError):
            pass

    return {"order_id": order.get("order_id", ""), "status": status,
            "issues": issues, "review": review, "compliant": not issues}


def classify_claim(issue_type: str, order: dict | None = None) -> dict:
    """Classify a return/refund/replacement claim against the policy. Wraps the
    resolution engine: qualifying (damaged/defect/printing error/wrong/lost) vs
    non-qualifying (change of mind, customer-approved details, image quality,
    normal print variation), attaching proof-approval evidence on customer
    fault."""
    from quoteforge.etsy.resolution import resolve_issue
    return resolve_issue(issue_type, order)


def monitor_orders(limit: int = 5000) -> dict:
    """Audit every order end to end. Returns the compliance summary: counts,
    violations (hard policy/state issues), and items needing individual review
    (cancellations after production, disputes, refunds)."""
    from quoteforge.db.database import init_db, get_all_orders
    init_db()
    orders = get_all_orders(limit)
    audits = [audit_order(o) for o in orders]
    violations = [{"order_id": a["order_id"], "status": a["status"],
                   "issues": a["issues"]} for a in audits if a["issues"]]
    review = [{"order_id": a["order_id"], "status": a["status"],
               "review": a["review"]} for a in audits if a["review"]]
    return {
        "checked": len(audits),
        "compliant": sum(1 for a in audits if a["compliant"]),
        "violations": violations,
        "needs_review": review,
    }


def format_monitor_text(report: dict) -> str:
    """Human-readable end-to-end order compliance report."""
    lines = ["=" * 60, "ORDER COMPLIANCE MONITOR", "=" * 60,
             f"  Orders checked : {report['checked']}",
             f"  Compliant      : {report['compliant']}",
             f"  Violations     : {len(report['violations'])}",
             f"  Needs review   : {len(report['needs_review'])}"]
    for v in report["violations"][:15]:
        lines.append(f"  [VIOLATION] {v['order_id']} ({v['status']})")
        for i in v["issues"]:
            lines.append(f"      - {i}")
    for r in report["needs_review"][:15]:
        lines.append(f"  [REVIEW] {r['order_id']} ({r['status']})")
        for i in r["review"]:
            lines.append(f"      - {i}")
    lines.append("=" * 60)
    return "\n".join(lines)


def run_monitor(send: bool = False) -> dict:
    """Run the monitor; email the owner when there are violations or review
    items (when send=True)."""
    report = monitor_orders()
    if send and (report["violations"] or report["needs_review"]):
        try:
            from quoteforge.automation.emailer import _send_email
            out = _send_email("⚠️ Order compliance: attention needed",
                              "<pre>" + format_monitor_text(report) + "</pre>")
            # A silently-dropped alert is worse than the original problem - if the
            # mailer skipped (creds unset) or errored, surface it in the logs.
            if isinstance(out, dict) and out.get("status") not in ("sent", "ok"):
                logger.warning("order-compliance alert not delivered: %s", out)
        except Exception as exc:  # noqa: BLE001
            logger.warning("order-compliance alert failed to send: %s", exc)
    return report
