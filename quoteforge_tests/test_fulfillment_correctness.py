"""REGRESSION: fulfillment-correctness fixes (v2 audit cluster 1).

Covers: multi-item revenue not replicated, wall-art order cost backfilled end to
end, a duplicate storefront confirm alerts the owner only once, and a cancelled
order never triggers a "shipped" buyer email.
"""
import json


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


# ── a multi-item basket must NOT record the order total on every line ─────────
def test_multiitem_basket_does_not_replicate_order_total(monkeypatch):
    # REGRESSION: order-level totals fell through to each line's sale_price, so a
    # 3-item basket recorded the full total 3x (revenue counted N times). Capture
    # exactly what each line receives: the basket totals must NOT be on it; the
    # shared CUSTOMER fields must be.
    import quoteforge.automation.webhook_server as ws
    captured = []
    monkeypatch.setattr(ws, "_run_one",
                        lambda merged, line_id: (captured.append(merged),
                                                 {"status": "success"})[1])
    ws.process_webhook_payload({
        "order_id": "MULTI", "customer_name": "Jen", "customer_email": "j@x.com",
        "total": "$90.00", "order_total": "$90.00",   # basket totals at ORDER level
        "items": [{"material": "Poster"}, {"material": "Poster"}, {"material": "Poster"}],
    })
    assert len(captured) == 3
    for m in captured:
        for total_field in ("total", "order_total", "grandtotal", "sale_price", "price"):
            assert m.get(total_field) is None, total_field   # no basket total on the line
        assert m.get("customer_email") == "j@x.com"          # but customer info IS shared


# ── wall-art order resolves a cost end to end (so the margin gate can fire) ────
def test_wallart_order_backfills_gelato_cost():
    # REGRESSION (PARTIAL fix hole): the resolver was tested but not the wiring -
    # pin that _build_order_data actually backfills a wall-art order's gelato_cost.
    from quoteforge.etsy.variations import build_variations
    from quoteforge.automation.webhook_server import _build_order_data
    v = build_variations()[0]                     # a poster variation
    label = "Poster" if v.material == "poster" else v.material
    data = _build_order_data({"material": label, "product_size": v.size,
                              "total": "$40.00"}, "W1")
    assert data.get("gelato_cost") and data["gelato_cost"] > 0


# ── a duplicate confirm of the same basket alerts the owner ONCE ──────────────
def test_duplicate_confirm_alerts_owner_once(tmp_path, monkeypatch):
    # REGRESSION (PARTIAL fix hole): the dedup stopped the double order/print but
    # _alert_owner still fired on every confirm. Only a NEW order should alert.
    _db(tmp_path, monkeypatch)
    import quoteforge.automation.design_confirm as dc
    calls = []
    monkeypatch.setattr(dc, "_alert_owner", lambda *a, **k: calls.append(1))
    dj = json.dumps({
        "contact": {"name": "Ann", "addr": "1 St, Atlanta GA", "country": "US", "state": "GA"},
        "cart": {"subtotal": 42.0, "items": 1, "lines": [{"fmt": "mug", "qty": 1}]}})
    dc.confirm_design("b@x.com", design_json=dj, design_id="cart-1", proof_image="")
    dc.confirm_design("b@x.com", design_json=dj, design_id="cart-2", proof_image="")  # same basket
    assert len(calls) == 1


# ── a cancelled order never triggers a "shipped" buyer email ─────────────────
def test_poll_cancel_does_not_push_shipped_email(tmp_path, monkeypatch):
    # REGRESSION (PARTIAL fix hole): the buyer "shipped" push ran before the cancel
    # branch, so a cancel arriving WITH tracking fired a misleading shipped email.
    db = _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-PC", "customer_email": "b@x.com",
                     "etsy_order_id": "E1", "recipient_name": "Ann", "occasion": "B"})
    db.update_order("QF-PC", status="in_production", gelato_order_id="GELX",
                    tracking_number="TN")
    import quoteforge.automation.fulfillment_tracker as ft
    pushed = []
    monkeypatch.setattr(ft, "get_all_orders",
                        lambda limit=500: [db.get_order("QF-PC")], raising=False)
    monkeypatch.setattr(ft, "_poll_vendor",
                        lambda o, gid: {"status": "canceled", "tracking_number": "TN"},
                        raising=False)
    monkeypatch.setattr(ft, "_retry_buyer_push",
                        lambda *a, **k: pushed.append(1), raising=False)
    ft.sync_tracking()
    assert pushed == []                           # no shipped push for a cancellation
    assert db.get_order("QF-PC")["status"] == "cancelled"
