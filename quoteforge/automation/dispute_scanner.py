"""Auto-detect Etsy disputes (refunds and open cases) on delivered orders.

A "delivered" scan from the carrier is not proof the order is problem-free: the
buyer can still open a case, request a refund, or complain after delivery. This
module reads Etsy's receipts feed, finds receipts that carry a refund or an open
case, matches them to QuoteForge orders, and flags those orders
``delivery_disputed`` — which suppresses the review request and keeps them out of
the clean-completion path.

Feasible scope: refund and case signals exposed on the receipt object. Free-text
complaint detection (buyer messages) needs Etsy's conversations API, which has
restricted access; that remains a deliberate, documented gap. All calls are
TEST_MODE-/credential-safe: without Etsy credentials the scan reports disabled
rather than erroring.
"""

# Receipt-level status strings that indicate an open Etsy case / dispute.
_CASE_STATUSES = {"open_case", "case_open", "disputed", "in_dispute", "case"}


def detect_disputes_from_receipts(receipts: list) -> list:
    """Return the Etsy receipt ids (as strings) that show a refund or open case.

    A receipt is disputed when it carries a non-empty ``refunds`` array or its
    ``status`` matches a known case/dispute string.
    """
    out: list = []
    for r in receipts or []:
        rid = str(r.get("receipt_id") or r.get("order_id") or "")
        if not rid:
            continue
        has_refund = bool(r.get("refunds"))
        status = str(r.get("status") or "").strip().lower()
        if has_refund or status in _CASE_STATUSES:
            out.append(rid)
    return out


def scan_etsy_disputes(receipts: list = None, limit: int = 100) -> dict:
    """Detect Etsy refunds/cases and flag the matching delivered orders disputed.

    Pass ``receipts`` directly (testing / cached feed), or leave it None to pull
    the recent receipts from Etsy. Without Etsy credentials the scan is disabled
    (no-op). Returns ``{status, disputed:[order_id, ...]}``.
    """
    from quoteforge.automation.etsy_api import _credentials_ready
    if receipts is None:
        if not _credentials_ready():
            return {"status": "disabled", "disputed": []}
        from quoteforge.automation.etsy_api import get_shop_receipts
        feed = get_shop_receipts(was_paid=True, was_shipped=True, limit=limit)
        receipts = feed.get("results", []) if isinstance(feed, dict) else (feed or [])

    from quoteforge.db.database import get_order_by_etsy_id
    from quoteforge.automation.fulfillment_tracker import mark_delivery_disputed
    disputed: list = []
    for rid in detect_disputes_from_receipts(receipts):
        order = get_order_by_etsy_id(rid)
        if not order or order.get("delivery_disputed"):
            continue
        mark_delivery_disputed(order["order_id"],
                               reason="Etsy refund/case detected on delivered order")
        disputed.append(order["order_id"])
    return {"status": "ok", "disputed": disputed}
