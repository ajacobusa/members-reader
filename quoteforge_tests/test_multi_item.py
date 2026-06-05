"""Tests for multi-item Etsy orders (several line items in one checkout)."""
from unittest.mock import patch

from quoteforge.automation.webhook_server import process_webhook_payload


def _db(tmp_path):
    import quoteforge.db.database as db
    return patch.object(db, "DB_PATH", tmp_path / "t.db"), \
        patch.object(db, "OUTPUT_DIR", tmp_path)


def test_multi_item_processes_each_line(tmp_path):
    import quoteforge.db.database as db
    p1, p2 = _db(tmp_path)
    with p1, p2, patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        payload = {
            "order_id": "ETSY100",
            "customer_name": "Jennifer",
            "customer_email": "jen@x.com",
            "items": [
                {"recipient_name": "Emma", "relationship": "Daughter",
                 "occasion": "Graduation"},
                {"recipient_name": "Liam", "relationship": "Son",
                 "occasion": "Birthday"},
            ],
        }
        result = process_webhook_payload(payload)
        orders = db.get_all_orders()
    assert result["status"] == "success"
    assert result["items"] == 2 and result["processed"] == 2
    # two distinct internal orders, both under the same Etsy order
    ids = {o["order_id"] for o in orders}
    assert "ETSY100-1" in ids and "ETSY100-2" in ids
    recipients = {o["recipient_name"] for o in orders}
    assert recipients == {"Emma", "Liam"}


def test_multi_item_inherits_order_level_customer(tmp_path):
    import quoteforge.db.database as db
    p1, p2 = _db(tmp_path)
    with p1, p2:
        db.init_db()
        process_webhook_payload({
            "order_id": "ETSY200", "customer_name": "Sam", "customer_email": "s@x.com",
            "items": [{"recipient_name": "Mom", "relationship": "Mother",
                       "occasion": "Mother's Day"}],
        })
        o = db.get_order("ETSY200-1")
    assert o["customer_name"] == "Sam"          # inherited from order level
    assert o["customer_email"] == "s@x.com"


def test_multi_item_is_idempotent_per_line(tmp_path):
    import quoteforge.db.database as db
    p1, p2 = _db(tmp_path)
    with p1, p2:
        db.init_db()
        payload = {"order_id": "ETSY300", "customer_name": "Ann",
                   "items": [{"recipient_name": "Kid", "occasion": "Birthday"}]}
        process_webhook_payload(payload)
        second = process_webhook_payload(payload)   # redelivery
        orders = [o for o in db.get_all_orders() if o["order_id"].startswith("ETSY300")]
    assert len(orders) == 1                          # no duplicate line item
    assert second["results"][0]["status"] == "duplicate"


def test_multi_item_partial_failure_reports(tmp_path):
    import quoteforge.db.database as db
    p1, p2 = _db(tmp_path)
    with p1, p2:
        db.init_db()
        result = process_webhook_payload({
            "order_id": "ETSY400", "customer_name": "Bo",
            "items": [
                {"recipient_name": "Good", "occasion": "Birthday"},
                {"relationship": "Son"},   # missing recipient_name + occasion
            ],
        })
    assert result["processed"] == 1
    statuses = [r["status"] for r in result["results"]]
    assert "success" in statuses and "error" in statuses


def test_single_item_still_works(tmp_path):
    import quoteforge.db.database as db
    p1, p2 = _db(tmp_path)
    with p1, p2:
        db.init_db()
        result = process_webhook_payload({
            "order_id": "SINGLE1", "customer_name": "Z",
            "recipient_name": "Ava", "occasion": "Graduation",
        })
    assert result["status"] == "success"
    assert result["order_id"] == "SINGLE1"
