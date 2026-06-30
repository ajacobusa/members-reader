"""Buyer-facing 'Order Delivered' notice: queued once on confirmed delivery, sent by
the gated customer-notify sweep, and customer-safe (no supplier/marketplace name)."""
import quoteforge.db.database as db
import quoteforge.automation.customer_notify as cn


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()


def test_delivered_template_exists_and_is_customer_safe():
    from quoteforge.etsy.customer_messages import get_base_template
    t = get_base_template("Order Delivered")
    assert t and "7 days" in t                       # policy-accurate coverage reminder
    low = t.lower()
    for banned in ("gelato", "printify", "printful", "etsy"):
        assert banned not in low                      # never name a supplier/marketplace


def test_queue_delivered_is_idempotent(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "D1", "customer_email": "a@b.com",
                     "recipient_name": "Sam"})
    assert cn.queue_order_delivered("D1", "Sam") is True
    assert cn.queue_order_delivered("D1", "Sam") is False     # already queued -> no dup
    msgs = [m for m in db.get_customer_messages("D1")
            if m["message_type"] == "Order Delivered"]
    assert len(msgs) == 1


def test_delivered_sent_once_by_gated_sweep(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "D2", "customer_email": "buyer@x.com",
                     "recipient_name": "Pat"})
    cn.queue_order_delivered("D2", "Pat")
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "CUSTOMER_AUTO_NOTIFY", True)
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    import quoteforge.automation.emailer as em
    sent = []
    monkeypatch.setattr(em, "_send_email",
                        lambda subj, html, to="": (sent.append((subj, to, html)),
                                                   {"status": "sent"})[1])
    res = cn.send_pending_notifications()
    assert "D2" not in res.get("skipped", [])
    assert len(sent) == 1
    subj, to, html = sent[0]
    assert "arrived" in subj.lower() and to == "buyer@x.com"
    assert "delivered" in html.lower()
    # REGRESSION: a second sweep must NOT resend (marked sent).
    sent.clear()
    cn.send_pending_notifications()
    assert sent == []


def test_leaky_delivered_body_is_blocked_at_send(tmp_path, monkeypatch):
    # REGRESSION: the runtime leak guard covers the delivered type too - a body that
    # somehow names a supplier/marketplace is SKIPPED, never emailed to the buyer.
    _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "D4", "customer_email": "b@x.com"})
    mid = db.save_customer_message("D4", "Order Delivered",
                                   "Your order shipped from Gelato!", sent=False)
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "CUSTOMER_AUTO_NOTIFY", True)
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    import quoteforge.automation.emailer as em
    sent = []
    monkeypatch.setattr(em, "_send_email",
                        lambda *a, **k: (sent.append(a), {"status": "sent"})[1])
    res = cn.send_pending_notifications()
    assert sent == []                              # leaky body never reaches the buyer
    assert mid in res.get("skipped", [])           # caught + skipped by the leak guard
    after = [m for m in db.get_customer_messages("D4") if m["id"] == mid][0]
    assert not after["sent"]                        # not marked sent (so it never goes)
