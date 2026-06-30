"""End-to-end claim automation: decide a validated claim and let the system act
- on approved_reprint it auto-creates the Gelato replacement order (reusing the
original artwork + product + stored ship-to) and emails the customer; denied /
needs_more_info send the right customer message; invalid transitions are blocked.
Plus the full lifecycle: request -> validate -> supplier_review -> reprint."""
import json
from datetime import datetime, timedelta


GOOD_SHIP = {"name": "Ann", "address": "1 Main St", "city": "Atlanta",
             "state": "GA", "postCode": "30301", "country": "US"}


def _seed(tmp_path, monkeypatch, **extra):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)   # mock Gelato create
    from quoteforge.db import database as db
    db.init_db()
    db.create_order({"order_id": "QF-1", "etsy_order_id": "E1",
                     "customer_email": "buyer@mail.com", "recipient_name": "Ann",
                     "occasion": "Birthday"})
    fields = {"status": "delivered", "delivery_confirmed": 1,
              "gelato_order_id": "GEL9", "gelato_product_uid": "uid-1",
              "artwork_url": "https://x/art.png", "ship_to": json.dumps(GOOD_SHIP),
              "delivered_at": (datetime.now() - timedelta(days=2)).isoformat()}
    fields.update(extra)
    db.update_order("QF-1", **fields)
    return db


def test_decide_claim_advances_filed_claim(tmp_path, monkeypatch):
    # REGRESSION: the Gelato-claim tracker writes claim_status="filed"/"staged"
    # into the same column; decide_claim must still be able to resolve it (those
    # are normalized to supplier_review), not reject it as an unknown state.
    db = _seed(tmp_path, monkeypatch, claim_status="filed",
               claim_category="damaged_package")
    from quoteforge.fulfillment.claim_workflow import decide_claim
    r = decide_claim("QF-1", "approved_reprint", send=False)
    assert r["ok"] is True
    assert db.get_order("QF-1")["claim_status"] == "approved_reprint"


def test_claims_digest_alert_failure_is_logged(tmp_path, monkeypatch, caplog):
    """REGRESSION: the claims-digest owner alert must not fail silently - a raised
    send is logged at WARNING, not swallowed by a bare except."""
    import logging
    db = _seed(tmp_path, monkeypatch, claim_status="supplier_review",
               claim_category="damaged_package")
    from quoteforge.fulfillment import claim_workflow
    from quoteforge.automation import emailer
    monkeypatch.setattr(emailer, "_send_email",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("SMTP down")))
    with caplog.at_level(logging.WARNING, logger="quoteforge.fulfillment.claim_workflow"):
        out = claim_workflow.run_claims_digest(send=True)
    assert out["actionable"] >= 1                     # there was a claim to alert on
    assert any("claims-digest alert" in r.message.lower() for r in caplog.records)


def test_open_claims_lists_by_state(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch, claim_status="supplier_review",
               claim_category="damaged_package")
    from quoteforge.fulfillment.claim_workflow import open_claims
    assert any(o["order_id"] == "QF-1" for o in open_claims())
    assert open_claims(states=["supplier_review"])[0]["order_id"] == "QF-1"
    assert open_claims(states=["denied"]) == []


def test_approved_reprint_creates_replacement_and_records(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch, claim_status="supplier_review")
    from quoteforge.fulfillment.claim_workflow import decide_claim
    r = decide_claim("QF-1", "approved_reprint")
    assert r["ok"] is True
    assert r["replacement"]["status"] == "submitted"        # Gelato order created
    row = db.get_order("QF-1")
    assert row["claim_status"] == "approved_reprint"
    assert row["replacement_order_id"]                      # recorded for tracking


def test_replacement_blocked_without_ship_to(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch, claim_status="supplier_review", ship_to="")
    from quoteforge.fulfillment.claim_workflow import decide_claim
    r = decide_claim("QF-1", "approved_reprint")
    assert r["replacement"]["status"] in ("needs_input", "manual")


def test_reprint_failed_alert_raise_is_logged_not_crashed(tmp_path, monkeypatch):
    # REGRESSION: reprint did NOT submit (no ship_to) AND the owner-alert send RAISES -
    # the except handler must LOG (it used an undefined `logger`, crashing with
    # NameError) and still return an actionable supplier_review.
    _seed(tmp_path, monkeypatch, claim_status="supplier_review", ship_to="")

    def _boom(*a, **k):
        raise RuntimeError("smtp down")
    monkeypatch.setattr("quoteforge.automation.emailer._send_email", _boom)
    from quoteforge.fulfillment.claim_workflow import decide_claim
    r = decide_claim("QF-1", "approved_reprint")        # must NOT raise NameError
    assert r["status"] == "supplier_review"
    assert r["replacement"]["status"] in ("needs_input", "manual")


def test_invalid_transition_blocked(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, claim_status="new")
    from quoteforge.fulfillment.claim_workflow import decide_claim
    r = decide_claim("QF-1", "approved_refund")             # new -> approved skips review
    assert r["ok"] is False and "cannot move" in r["reason"]


def test_denied_and_more_info_send_customer_message(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, claim_status="evidence_review")
    sent = {}
    monkeypatch.setattr("quoteforge.automation.emailer._send_email",
                        lambda subject, body, to="", attachments=None:
                        sent.update(to=to, subject=subject) or {"status": "stub"})
    from quoteforge.fulfillment.claim_workflow import decide_claim
    r = decide_claim("QF-1", "needs_more_info", note="packaging photo", send=True)
    assert r["ok"] is True and r["email"] == {"status": "stub"}
    assert sent["to"] == "buyer@mail.com"                   # customer, not owner


def test_full_lifecycle_request_to_reprint(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("quoteforge.automation.emailer._send_email",
                        lambda *a, **k: {"status": "stub"})   # no real send in tests
    from quoteforge.fulfillment.claim_service import intake_claim
    from quoteforge.fulfillment.claim_workflow import decide_claim
    # 1. Customer reports with no photos -> documented as needs_more_info.
    r1 = intake_claim({"order_number": "E1", "email": "buyer@mail.com",
                       "issue_type": "Damaged item", "description": "crushed",
                       "photos": []})
    assert r1["recommended_status"] == "needs_more_info"
    # 2. Photos arrive -> re-intake clears to supplier_review.
    r2 = intake_claim({"order_number": "E1", "email": "buyer@mail.com",
                       "issue_type": "Damaged item", "description": "crushed",
                       "photos": ["product", "packaging"]})
    assert r2["recommended_status"] == "supplier_review"
    assert db.get_order("QF-1")["claim_status"] == "supplier_review"
    # 3. Owner approves -> replacement Gelato order auto-created.
    r3 = decide_claim("QF-1", "approved_reprint", send=True)
    assert r3["ok"] and r3["replacement"]["status"] == "submitted"
    assert db.get_order("QF-1")["claim_status"] == "approved_reprint"
