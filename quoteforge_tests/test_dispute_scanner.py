"""Auto-detect Etsy refunds/cases on delivered orders and mark them disputed
(so they aren't treated as clean completions and no review is requested).
Feasible via the Etsy receipts feed; disabled gracefully without credentials."""


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_detect_disputes_from_receipts():
    from quoteforge.automation.dispute_scanner import detect_disputes_from_receipts
    receipts = [
        {"receipt_id": 100, "refunds": [{"amount": 1899}]},   # refunded
        {"receipt_id": 101, "refunds": []},                   # clean
        {"receipt_id": 102, "status": "open_case"},           # case
    ]
    ids = detect_disputes_from_receipts(receipts)
    assert "100" in ids and "102" in ids and "101" not in ids


def test_scan_marks_matching_order_disputed(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-9", "etsy_order_id": "100",
                     "recipient_name": "A", "occasion": "B"})
    db.update_order("QF-9", status="delivered", delivery_confirmed=1)
    from quoteforge.automation.dispute_scanner import scan_etsy_disputes
    r = scan_etsy_disputes(receipts=[{"receipt_id": 100, "refunds": [{"amount": 1}]}])
    assert "QF-9" in r["disputed"]
    assert db.get_order("QF-9")["delivery_disputed"] == 1
    # And the review is now suppressed for it.
    from quoteforge.etsy.delight_loop import delight_due
    assert not any(d["order_id"] == "QF-9" for d in delight_due(db.get_all_orders(50)))


def test_scan_disabled_without_credentials(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("quoteforge.config.ETSY_API_KEY", "")
    monkeypatch.setattr("quoteforge.config.ETSY_SHOP_ID", "")
    from quoteforge.automation.dispute_scanner import scan_etsy_disputes
    r = scan_etsy_disputes()          # no receipts passed, no creds
    assert r["status"] == "disabled"
