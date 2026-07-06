"""Customer-satisfaction & best-practice hardening (the 'implement all' pass):
- #13b /upload rejects a non-image disguised by extension (decode-integrity + bomb guard)
- #16b transactional lifecycle notifications auto-send (config-gated, idempotent, no leak)
All network/IO mocked or tmp.
"""
import pytest


def test_upload_rejects_non_image_disguised_as_jpg(tmp_path, monkeypatch):
    # #13b: garbage bytes named .jpg pass the extension check but must be rejected as
    # an unusable image (decode-integrity guard), not crash or get processed.
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    import io
    buf = io.BytesIO(b"definitely not an image " * 20)
    buf.seek(0)
    r = app.test_client().post("/upload", data={"email": "b@x.com", "size": "8x10",
        "file": (buf, "evil.jpg")}, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "usable image" in (r.get_json() or {}).get("message", "")


# ---------------------------------------------------------- #16b notifications
def _seed_msgs(db):
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,customer_email) "
                 "VALUES (?,?,?,?)", ("O1", "Ann", "Birthday", "buyer@x.com"))
    conn.commit()
    conn.close()
    db.save_customer_message("O1", "Order Received", "Thank you for your order!")
    db.save_customer_message("O1", "In Production", "Your design is being made.")
    db.save_customer_message("O1", "Order Shipped", "It shipped.")   # NOT auto-sent


def test_notify_is_noop_when_disabled(tmp_path, monkeypatch):
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(cfg, "CUSTOMER_AUTO_NOTIFY", False)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    _seed_msgs(db)
    from quoteforge.automation.customer_notify import send_pending_notifications
    r = send_pending_notifications()
    assert r["enabled"] is False and r["sent"] == []     # hard no-op


def test_notify_sends_only_transactional_types_and_is_idempotent(tmp_path, monkeypatch):
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(cfg, "CUSTOMER_AUTO_NOTIFY", True)
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    _seed_msgs(db)
    import quoteforge.automation.customer_notify as cn
    seen = []
    monkeypatch.setattr(cn, "_send_email",
                        lambda subj, html, to="", **_kw: (seen.append((to, subj)),
                                                          {"status": "sent"})[1], raising=False)
    # patch the lazily-imported name
    import quoteforge.automation.emailer as em
    monkeypatch.setattr(em, "_send_email",
                        lambda subj, html, to="", **_kw: (seen.append((to, subj)),
                                                          {"status": "sent"})[1])
    r = cn.send_pending_notifications()
    assert len(r["sent"]) == 2                            # Order Received + In Production
    assert all(to == "buyer@x.com" for to, _ in seen)
    # idempotent: a second run sends nothing new (the two are marked sent)
    seen.clear()
    r2 = cn.send_pending_notifications()
    assert r2["sent"] == [] and seen == []


def test_notify_skips_supplier_leak(tmp_path, monkeypatch):
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    import quoteforge.automation.emailer as em
    monkeypatch.setattr(cfg, "CUSTOMER_AUTO_NOTIFY", True)
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,customer_email) "
                 "VALUES (?,?,?,?)", ("O1", "Ann", "B", "buyer@x.com"))
    conn.commit()
    conn.close()
    db.save_customer_message("O1", "Order Received", "Your order ships via Gelato soon")
    sent = []
    monkeypatch.setattr(em, "_send_email",
                        lambda subj, html, to="": (sent.append(to), {"status": "sent"})[1])
    from quoteforge.automation.customer_notify import send_pending_notifications
    r = send_pending_notifications()
    assert sent == [] and len(r["skipped"]) == 1         # leak never sent
