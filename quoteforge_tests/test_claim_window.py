"""Claim reporting-deadline (time-window) policy on top of the fault/outcome
resolution engine. Customer auto-accept window 7 days from the delivery anchor
(a 23-day buffer inside Gelato Create's 30-day guarantee); 8-30 is the buffer
zone -> manual review (Gelato may still pay); past 30 needs management approval
and the partner won't reimburse (goodwill/at-cost).

Anchors: carrier-confirmed delivery date when we have it; otherwise the
estimated-delivery date (assumed-delivered orders with no carrier timestamp)."""
from datetime import datetime, timedelta

from quoteforge.etsy.resolution import claim_window, resolve_issue


def _delivered(days_ago: int, confirmed: int = 1) -> dict:
    d = (datetime.now() - timedelta(days=days_ago)).isoformat()
    return {"order_id": "X", "delivery_confirmed": confirmed, "delivered_at": d}


def test_within_customer_window_is_eligible():
    # 0..7 days -> auto-accept (keeps the >=23-day buffer before Gelato's 30d).
    w = claim_window(_delivered(5))
    assert w["eligibility"] == "eligible"
    assert w["anchor_type"] == "carrier_confirmed"
    assert w["within_supplier_window"] is True
    assert claim_window(_delivered(7))["eligibility"] == "eligible"    # boundary


def test_reported_at_delivery_is_eligible():
    assert claim_window(_delivered(0))["eligibility"] == "eligible"


def test_buffer_zone_8_to_30_is_manual_review():
    assert claim_window(_delivered(8))["eligibility"] == "manual_review"   # boundary
    assert claim_window(_delivered(25))["eligibility"] == "manual_review"
    w = claim_window(_delivered(30))                    # boundary, Gelato still pays
    assert w["eligibility"] == "manual_review"
    assert w["within_supplier_window"] is True          # 30 <= 30


def test_past_gelato_window_is_management_approval_and_unfunded():
    w = claim_window(_delivered(35))
    assert w["eligibility"] == "management_approval"
    assert w["within_supplier_window"] is False         # past 30d -> no reimbursement


def test_assumed_delivery_anchors_to_estimated_delivery():
    eta = (datetime.now() - timedelta(days=25)).date().isoformat()
    w = claim_window({"order_id": "Y", "delivery_confirmed": 0,
                      "estimated_delivery": eta})
    assert w["anchor_type"] == "estimated_delivery"
    assert w["eligibility"] == "manual_review"           # 25 -> buffer zone


def test_carrier_confirmed_preferred_over_estimated():
    o = _delivered(2)
    o["estimated_delivery"] = (datetime.now() - timedelta(days=30)).date().isoformat()
    assert claim_window(o)["anchor_type"] == "carrier_confirmed"


def test_no_date_is_unknown_and_not_blocked():
    w = claim_window({"order_id": "Z"})
    assert w["eligibility"] == "unknown"
    assert w["within_supplier_window"] is True           # can't tell -> don't block


def test_explicit_report_date_is_used():
    w = claim_window({"delivery_confirmed": 1,
                      "delivered_at": "2026-06-01T10:00:00"},
                     report_date="2026-06-05")
    assert w["days_elapsed"] == 4 and w["eligibility"] == "eligible"


def test_resolve_issue_attaches_claim_window():
    res = resolve_issue("damaged", _delivered(2))
    assert res["claim_window"]["eligibility"] == "eligible"


def test_resolve_issue_without_order_has_no_window():
    res = resolve_issue("damaged")
    assert res["claim_window"] is None
