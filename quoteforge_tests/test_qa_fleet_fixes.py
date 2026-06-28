"""Fixes from the 8-agent QA fleet (find->verify):
- HIGH: daily price sync must read the US/USD qty-1 cost, not a global min across
        currencies/countries/tiers (could under-price the retail listing).
- LOW:  a carrier exception (return-to-sender / failed delivery) surfaces for an owner
        alert immediately, instead of waiting 10-21 days for stale-in-transit.
"""
import sqlite3


def test_usd_unit_cost_ignores_foreign_currency_and_bulk():
    from quoteforge.automation.gelato_sync import _usd_unit_cost
    rows = [
        {"currency": "EUR", "country": "DE", "quantity": 1, "price": 6.50},   # smaller, foreign
        {"currency": "USD", "country": "US", "quantity": 1, "price": 9.50},   # the right one
        {"currency": "USD", "country": "US", "quantity": 50, "price": 4.00},  # bulk tier
    ]
    assert _usd_unit_cost(rows) == 9.50           # not the 6.50 EUR, not the 4.00 bulk
    assert _usd_unit_cost([]) is None
    assert _usd_unit_cost([{"currency": "EUR", "price": 5.0}]) is None   # no USD -> record nothing


def test_carrier_exception_surfaces_for_alert(tmp_path, monkeypatch):
    import quoteforge.config as cfg
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        "INSERT INTO orders (order_id,recipient_name,occasion,status,vendor,"
        "vendor_order_id,tracking_number,shipped_at) VALUES (?,?,?,?,?,?,?,?)",
        ("O1", "R", "B", "shipped", "gelato", "G1", "TN1", "2026-06-01T00:00:00"))
    conn.commit()
    conn.close()
    monkeypatch.setattr(cfg, "TRACKING_API_KEY", "k", raising=False)
    import quoteforge.automation.fulfillment_tracker as ft
    import quoteforge.fulfillment.tracking_api as ta
    monkeypatch.setattr(ft, "_poll_vendor",
                        lambda o, gid: {"tracking_number": "TN1", "status": "shipped"})
    monkeypatch.setattr(ta, "carrier_detail",
                        lambda tn, c: {"status": "exception", "detail": "return to sender"})
    r = ft.sync_tracking()
    assert "O1" in r["delivery_exception"]        # surfaced immediately, not in 10-21 days
    assert db.get_order("O1")["status"] != "delivered"   # NEVER falsely delivered
