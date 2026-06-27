"""Expert E2E improvements implemented from the recommendation list:
- #3 registry descriptor completion (room-mockup flag on Family)
- #4 per-line financials (true margin per item in a multi-item basket)
- #5 Sentry wiring (swallowed pipeline/thread exceptions now reported)
- #1 submit_unconfirmed reconcile tool (operator promotes or re-queues)
"""
import json
import sqlite3


# --------------------------------------------------------- #3 registry descriptor
def test_family_room_mockup_flag():
    from quoteforge.etsy.families import family_for
    assert family_for("apparel").room_mockup is False    # a room-on-wall mockup is meaningless
    assert family_for("mug").room_mockup is True          # behaviour preserved (was != apparel)


# ------------------------------------------------------------- #4 per-line P&L
def test_line_financials_per_line_pnl():
    from quoteforge.etsy.financials import line_financials
    order = {"line_items": json.dumps([
        {"title": "Poster", "unit": 25.0, "qty": 2, "gelato_cost": 8.0},
        {"title": "Mug", "unit": 18.0, "qty": 1, "gelato_cost": 6.0}])}
    lf = line_financials(order)
    assert len(lf) == 2
    assert lf[0]["revenue"] == 50.0 and lf[0]["gelato_cost"] == 16.0
    assert lf[0]["gross_profit"] == 34.0           # 50 revenue - 16 COGS (cost x qty)
    assert lf[1]["revenue"] == 18.0 and lf[1]["gross_profit"] == 12.0
    assert line_financials({}) == []                # single-item / no lines


# ------------------------------------------------------------- #5 Sentry wiring
def test_background_failure_reports_to_monitoring(monkeypatch):
    import quoteforge.automation.webhook_server as ws
    import quoteforge.automation.monitoring as mon
    captured = []
    monkeypatch.setattr(mon, "capture", lambda exc: captured.append(exc))

    def _boom(_p):
        raise RuntimeError("boom")
    monkeypatch.setattr(ws, "process_webhook_payload", _boom)
    ws._process_in_background({})                    # must swallow AND report
    assert captured and isinstance(captured[0], RuntimeError)


# -------------------------------------------------- #1 reconcile-unconfirmed tool
def _seed_unconfirmed(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,status) "
                 "VALUES (?,?,?,?)", ("O1", "R", "B", "submit_unconfirmed"))
    conn.commit()
    conn.close()
    return db


def test_reconcile_landed_promotes_to_in_production(tmp_path, monkeypatch):
    db = _seed_unconfirmed(tmp_path, monkeypatch)
    from quoteforge import admin
    admin.main(["reconcile-unconfirmed", "O1", "landed", "GLT-9"])
    o = db.get_order("O1")
    assert o["status"] == "in_production" and o["vendor_order_id"] == "GLT-9"


def test_reconcile_not_landed_queues_for_retry(tmp_path, monkeypatch):
    db = _seed_unconfirmed(tmp_path, monkeypatch)
    from quoteforge import admin
    admin.main(["reconcile-unconfirmed", "O1", "not-landed"])
    assert db.get_order("O1")["status"] == "error"   # retry-fulfillment job re-submits it
