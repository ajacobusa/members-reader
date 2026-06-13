"""Staged win-back campaign: Day 60 'new designs' (no coupon) -> Day 90 10%
coupon -> Day 120 final 15% offer. Each stage fires ONCE per customer
(idempotent); a new order resets the customer (they're active again)."""
from datetime import datetime, timedelta

from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _order(db, oid, email, days_ago):
    db.create_order({"order_id": oid, "customer_email": email,
                     "customer_name": "Cust", "recipient_name": "R",
                     "occasion": "Birthday", "sale_price": 40})
    old = (datetime.now() - timedelta(days=days_ago)).isoformat()
    db.update_order(oid, status="delivered", created_at=old)


def test_stage_1_at_60_days_no_coupon(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _order(db, "W1", "a@b.com", 65)
    from quoteforge.marketing.winback import due_winbacks
    due = due_winbacks()
    item = next(d for d in due if d["email"] == "a@b.com")
    assert item["stage"] == 1 and item["coupon"] is None


def test_stage_escalates_to_coupon_then_final(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _order(db, "W2", "c@b.com", 95)               # past 90 -> stage 2
    from quoteforge.marketing import winback as wb
    r1 = wb.run_winback(send=True)
    s2 = next(x for x in r1["sent_items"] if x["email"] == "c@b.com")
    assert s2["stage"] == 2 and s2["coupon"] == "COMEBACK10"
    # Re-run: same age -> nothing new for c@b.com
    assert not any(x["email"] == "c@b.com" for x in wb.run_winback(send=True)["sent_items"])
    # Age to 125 days -> final stage 3 @ 15%
    with db._conn() as cx:
        old = (datetime.now() - timedelta(days=125)).isoformat()
        cx.execute("UPDATE orders SET created_at=? WHERE customer_email=?",
                   (old, "c@b.com"))
    r3 = wb.run_winback(send=True)
    s3 = next(x for x in r3["sent_items"] if x["email"] == "c@b.com")
    assert s3["stage"] == 3 and s3["coupon"] == "COMEBACK15"


def test_active_customer_not_targeted(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _order(db, "W3", "active@b.com", 10)          # recent
    from quoteforge.marketing.winback import due_winbacks
    assert not any(d["email"] == "active@b.com" for d in due_winbacks())


def test_new_order_reactivates_and_resets(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    _order(db, "W4", "back@b.com", 95)
    from quoteforge.marketing import winback as wb
    wb.run_winback(send=True)                     # stage 2 sent
    _order(db, "W4b", "back@b.com", 1)            # they came back today
    # No longer lapsed -> not targeted; stage history cleared for next lapse
    assert not any(d["email"] == "back@b.com" for d in wb.due_winbacks())
