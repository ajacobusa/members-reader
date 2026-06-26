"""REGRESSION: proof/print + resilience fixes (v2 audit cluster 3)."""
import requests


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


GOOD_ADDR = {"name": "Ann", "address": "1 St", "city": "Atlanta",
             "state": "GA", "postCode": "30301", "country": "US"}


def test_gelato_timeout_marks_unconfirmed_and_blocks_resubmit(tmp_path, monkeypatch):
    # REGRESSION: a timeout AFTER the POST (the vendor may already have the order)
    # must NOT return 'error' - a later owner re-run would blindly re-submit and
    # double-print + double-charge. It marks 'submit_unconfirmed' and a re-run is
    # held for manual reconciliation (the vendor is never hit twice).
    db = _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-TO", "customer_email": "b@x.com",
                     "recipient_name": "Ann", "occasion": "B"})
    calls = []

    def _timeout(*a, **k):
        calls.append(1)
        raise requests.exceptions.Timeout("read timed out after POST")
    monkeypatch.setattr("quoteforge.automation.gelato_api.create_gelato_order",
                        _timeout, raising=False)
    import quoteforge.fulfillment.router as router
    order = {"order_id": "QF-TO", "vendor": "gelato",
             "gelato_product_uid": "uid-real", "product_type": "print"}

    r1 = router.route_order(order, recipient=GOOD_ADDR, artwork_url="https://x/y.png")
    assert r1["status"] == "submit_unconfirmed"
    assert db.get_order("QF-TO")["status"] == "submit_unconfirmed"

    r2 = router.route_order(order, recipient=GOOD_ADDR, artwork_url="https://x/y.png")
    assert r2["status"] == "manual"                 # re-run held, not re-submitted
    assert len(calls) == 1                          # vendor hit exactly once


def test_clean_4xx_still_errors_and_can_retry(tmp_path, monkeypatch):
    # A definite NON-submission (4xx, vendor rejected before creating) stays 'error'
    # (safe to retry after fixing) - it must NOT be treated as unconfirmed.
    db = _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-4XX", "customer_email": "b@x.com",
                     "recipient_name": "Ann", "occasion": "B"})

    def _badreq(*a, **k):
        resp = requests.Response()
        resp.status_code = 400
        raise requests.exceptions.HTTPError("400 bad request", response=resp)
    monkeypatch.setattr("quoteforge.automation.gelato_api.create_gelato_order",
                        _badreq, raising=False)
    import quoteforge.fulfillment.router as router
    order = {"order_id": "QF-4XX", "vendor": "gelato",
             "gelato_product_uid": "uid-real", "product_type": "print"}
    r = router.route_order(order, recipient=GOOD_ADDR, artwork_url="https://x/y.png")
    assert r["status"] == "error"
