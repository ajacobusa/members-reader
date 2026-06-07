"""Tests for per-vendor floors, fulfillment routing, and AI ops review."""


def test_per_vendor_floor(monkeypatch):
    from quoteforge.catalog.registry import floor_for_vendor
    monkeypatch.setattr("quoteforge.config.VENDOR_MARGIN_FLOORS_JSON", "", raising=False)
    assert floor_for_vendor("gelato") == 60.0       # global floor
    assert floor_for_vendor("service") == 80.0      # default service floor
    assert floor_for_vendor("digital") == 90.0
    monkeypatch.setattr("quoteforge.config.VENDOR_MARGIN_FLOORS_JSON",
                        '{"printful":55,"service":85}', raising=False)
    assert floor_for_vendor("printful") == 60.0     # override below 60 clamped up
    assert floor_for_vendor("service") == 85.0


def test_router_gelato_manual_when_incomplete(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "1", "vendor": "gelato"})
    assert r["status"] == "manual" and r["vendor"] == "gelato"


def test_router_printful_manual_without_key(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "2", "vendor": "printful"},
                    recipient={"name": "A"}, artwork_url="http://x/a.png")
    assert r["status"] == "manual" and r["vendor"] == "printful"


def test_router_digital_fulfilled():
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "3", "vendor": "digital"})
    assert r["status"] == "fulfilled" and r["vendor"] == "digital"


def test_ai_review_runs_with_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.automation.ai_ops_review import ai_review, collect_signals
    sig = collect_signals()
    assert "orders_by_status" in sig and "margins" in sig and "pnl_month" in sig
    r = ai_review(email=False)
    assert r["findings"] and isinstance(r["plan"], str) and r["plan"]


def test_ai_review_command_registered():
    from quoteforge import admin
    assert "ai-review" in admin.COMMANDS
