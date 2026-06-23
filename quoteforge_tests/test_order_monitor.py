"""End-to-end order compliance monitor: validates every order against the
Approval -> Production -> Cancellation -> Return/Refund policy and the
fulfillment state machine, flagging violations and review-required requests."""
from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_production_without_approval_is_a_violation():
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "X", "status": "in_production",
                     "proof_approved": 0, "vendor_order_id": "G1"})
    assert not a["compliant"]
    assert any("approval" in i.lower() for i in a["issues"])


def test_compliant_order_passes():
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "Y", "status": "delivered",
                     "proof_approved": 1, "vendor_order_id": "G2",
                     "delivery_confirmed": 1, "delivered_at": "2026-06-10"})
    assert a["compliant"] and not a["issues"]


def test_cancellation_after_production_needs_review():
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "Z", "status": "cancelled",
                     "vendor_order_id": "G3"})
    assert any("after production" in r.lower() for r in a["review"])


def test_delivered_but_disputed_flagged():
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "D", "status": "delivered",
                     "proof_approved": 1, "vendor_order_id": "G4",
                     "delivery_confirmed": 1, "delivered_at": "x",
                     "delivery_disputed": 1})
    assert any("disput" in r.lower() for r in a["review"])


def test_delivered_without_confirmation_is_violation():
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "E", "status": "delivered",
                     "proof_approved": 1, "vendor_order_id": "G5"})
    assert not a["compliant"]


def test_claim_classification_uses_policy():
    """Qualifying vs non-qualifying claims follow the resolution policy, with
    customer-approval evidence attached for customer-fault denials."""
    from quoteforge.automation.order_monitor import classify_claim
    dmg = classify_claim("damaged", {"order_id": "C1"})
    assert dmg["recognized"] and dmg["customer_pays"] is False   # shop covers damage
    typo = classify_claim("wrong_personalization",
                          {"order_id": "C2", "proof_approved": 1,
                           "proof_approved_at": "2026-06-01"})
    assert typo["fault"] == "customer" and typo["evidence"]      # approved -> denial supported


def test_monitor_orders_aggregates(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "M1", "recipient_name": "A", "occasion": "B"})
    db.update_order("M1", status="in_production", vendor_order_id="G1")  # no approval
    db.create_order({"order_id": "M2", "recipient_name": "B", "occasion": "C"})
    db.update_order("M2", status="delivered", proof_approved=1,
                    vendor_order_id="G2", delivery_confirmed=1, delivered_at="x")
    from quoteforge.automation.order_monitor import monitor_orders
    r = monitor_orders()
    assert r["checked"] == 2
    assert "M1" in [v["order_id"] for v in r["violations"]]
    assert "M2" not in [v["order_id"] for v in r["violations"]]


def test_approved_but_unrouted_order_is_surfaced():
    # REGRESSION (#7): a customer-approved recorded sale stuck at 'received' with no
    # vendor order id must be flagged for review - direct/WEB orders were silently
    # frozen (nothing downstream fulfils a no-vendor order).
    from quoteforge.automation.order_monitor import audit_order
    a = audit_order({"order_id": "WEB-1", "status": "received",
                     "proof_approved": 1, "sale_price": 42.0})
    assert any("not submitted to the print partner" in r for r in a["review"])
    # an order still awaiting approval is NOT flagged (legitimately waiting)
    b = audit_order({"order_id": "WEB-2", "status": "received", "sale_price": 42.0})
    assert not any("not submitted" in r for r in b["review"])
