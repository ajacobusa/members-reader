"""Owner per-order notices: an INVOICE copy on placement and a SHIPPED + tracking copy
on ship, to ORDER_NOTIFY_EMAIL. Idempotent (a per-order flag, no double-send) and
best-effort (a send failure never blocks the order and retries next run)."""
import quoteforge.automation.owner_notify as on
import quoteforge.db.database as db


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()


def test_customer_id_assigned_and_stable(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "O1", "customer_email": "Buyer@Example.com",
                     "occasion": "B"})
    db.create_order({"order_id": "O2", "customer_email": "  buyer@example.com "})
    o1, o2 = db.get_order("O1"), db.get_order("O2")
    assert o1["customer_id"].startswith("CUST-")
    assert o1["customer_id"] == o2["customer_id"]          # same buyer -> same id


def test_customer_id_unique_and_stable(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    i1 = db.get_or_create_customer("x@a.com")
    i1b = db.get_or_create_customer(" X@A.com ")           # normalized -> same id
    i2 = db.get_or_create_customer("y@b.com")              # different buyer -> different
    assert i1 == i1b and i1 != i2
    a1 = db.get_or_create_customer("", anon_key="O-1")
    a2 = db.get_or_create_customer("", anon_key="O-2")     # anon -> unique per order
    assert a1 != a2


def test_customer_id_collision_is_disambiguated(tmp_path, monkeypatch):
    # REGRESSION: two DIFFERENT emails that hash to the SAME base must still be unique.
    _db(tmp_path, monkeypatch)
    monkeypatch.setattr(db, "_derive_customer_id", lambda *a, **k: "CUST-collide")
    i1 = db.get_or_create_customer("a@a.com")
    i2 = db.get_or_create_customer("b@b.com")
    assert i1 == "CUST-collide" and i2 == "CUST-collide-2" and i1 != i2


def test_delivered_email_sends_once(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "D1", "customer_email": "a@b.com",
                     "product_type": "poster"})
    db.update_order("D1", status="delivered", delivery_confirmed=1,
                    delivered_at="2026-06-30")
    cap = {}
    monkeypatch.setattr(on, "_send",
                        lambda s, h: (cap.update(s=s, h=h), {"status": "sent"})[1])
    assert on.send_owner_delivered("D1")["status"] == "sent"
    assert "D1" in cap["h"]
    assert db.get_order("D1")["owner_delivered_emailed"] == 1
    assert on.send_owner_delivered("D1")["status"] == "already_sent"   # idempotent


def test_invoice_sends_once_then_flagged(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "I1", "customer_email": "a@b.com",
                     "product_type": "poster", "sale_price": 24.0})
    sent = []
    monkeypatch.setattr(on, "_send",
                        lambda *a, **k: (sent.append(a), {"status": "sent"})[1])
    r1 = on.send_owner_invoice("I1")
    assert r1["status"] == "sent" and len(sent) == 1
    assert db.get_order("I1")["owner_invoice_emailed"] == 1
    # REGRESSION: a second call (webhook retry) must NOT re-send.
    r2 = on.send_owner_invoice("I1")
    assert r2["status"] == "already_sent" and len(sent) == 1


def test_shipped_sends_once_with_tracking(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "S1", "customer_email": "a@b.com",
                     "product_type": "mug"})
    db.update_order("S1", tracking_number="1Z999", carrier="ups", status="shipped")
    captured = {}
    monkeypatch.setattr(on, "_send", lambda subj, html: captured.update(
        subject=subj, html=html) or {"status": "sent"})
    r = on.send_owner_shipped("S1")
    assert r["status"] == "sent"
    assert "1Z999" in captured["html"]                    # tracking number in the email
    assert "1Z999" in captured["subject"]
    assert db.get_order("S1")["owner_shipped_emailed"] == 1
    assert on.send_owner_shipped("S1")["status"] == "already_sent"   # idempotent


def test_send_failure_does_not_flag_so_it_retries(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "F1", "customer_email": "a@b.com"})

    def _boom(*a, **k):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(on, "_send", _boom)
    r = on.send_owner_invoice("F1")                       # best-effort: never raises
    assert r["status"] == "error"
    assert db.get_order("F1")["owner_invoice_emailed"] == 0   # not flagged -> retries


def test_tracking_url_is_universal():
    assert on.tracking_url("ups", "1Z999").endswith("1Z999")
    assert on.tracking_url("", "") == ""
