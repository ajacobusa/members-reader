"""REGRESSION suite for the end-to-end order-lifecycle audit fixes.

Each test pins one adversarially-confirmed issue from the multi-agent audit so it
can't silently regress. One money/dispute/leak risk per test, named after it.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


GOOD_ADDR = {"name": "Ann", "address": "1 St", "city": "Atlanta",
             "state": "GA", "postCode": "30301", "country": "US"}


# ── #11: Gelato webhook 'delivered' must confirm delivery (not assumed) ──────
def test_gelato_webhook_delivered_stamps_delivery_confirmed(tmp_path, monkeypatch):
    # REGRESSION: the webhook path marked status='delivered' but left
    # delivery_confirmed=0 / delivered_at NULL, so the review ask was delayed ~7
    # days as an ASSUMED delivery.
    db = _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-D", "customer_email": "b@x.com",
                     "recipient_name": "Ann", "occasion": "Birthday"})
    from quoteforge.automation.webhook_server import process_gelato_callback
    process_gelato_callback({"orderReferenceId": "QF-D", "status": "delivered"})
    o = db.get_order("QF-D")
    assert o["status"] == "delivered"
    assert o["delivery_confirmed"] == 1 and o["delivered_at"]


# ── #12: poll path normalizes Gelato 'canceled' to terminal 'cancelled' ──────
def test_poll_path_marks_gelato_canceled_terminal(tmp_path, monkeypatch):
    # REGRESSION: sync_tracking only handled 'delivered'; a Gelato 'canceled'
    # (one L) left the order non-terminal forever (re-polled, never reported).
    db = _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-C", "customer_email": "b@x.com",
                     "recipient_name": "Ann", "occasion": "Birthday"})
    db.update_order("QF-C", status="in_production", gelato_order_id="GELX",
                    tracking_number="TN1")
    import quoteforge.automation.fulfillment_tracker as ft
    monkeypatch.setattr(ft, "get_all_orders",
                        lambda limit=500: [db.get_order("QF-C")], raising=False)
    monkeypatch.setattr(ft, "_poll_vendor",
                        lambda o, gid: {"status": "canceled", "tracking_number": "TN1"},
                        raising=False)
    ft.sync_tracking()
    assert db.get_order("QF-C")["status"] == "cancelled"


# ── #13: a missing-item claim needs at least the product photo ───────────────
def test_missing_item_claim_requires_product_photo(tmp_path, monkeypatch):
    # REGRESSION: incomplete_order required ZERO photos, so a missing-item claim
    # was recommended straight to supplier_review evidence-complete (Gelato bounces
    # it for missing photos).
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    db.create_order({"order_id": "QF-M", "etsy_order_id": "EM",
                     "customer_email": "b@x.com", "recipient_name": "Ann",
                     "occasion": "Birthday"})
    db.update_order("QF-M", status="delivered", delivery_confirmed=1,
                    gelato_order_id="GEL9",
                    delivered_at=(datetime.now() - timedelta(days=2)).isoformat())
    from quoteforge.fulfillment.claim_service import validate_claim_request
    r = validate_claim_request({"order_number": "EM", "name": "Ann",
                                "email": "b@x.com", "issue_type": "Missing item",
                                "description": "one missing", "photos": []})
    assert r["checks"]["evidence_complete"] is False
    assert r["recommended_status"] != "supplier_review"


# ── #4: margin floor enforced at the pre-vendor gate (held, not just flagged) ─
def test_below_floor_order_is_held_at_fulfillment_gate(monkeypatch):
    # REGRESSION: the floor was only checked by the read-only scheduled monitor,
    # AFTER the vendor charge. A below-floor order must be HELD here.
    from quoteforge.automation.pipeline_orchestrator import validate_for_fulfillment
    bad = validate_for_fulfillment(
        {"product_type": "print", "print_quality": "approve",
         "sale_price": 10.0, "gelato_cost": 9.0}, GOOD_ADDR, "uid", "https://x/y.png")
    assert not bad["ok"] and any("margin" in i.lower() for i in bad["issues"])
    good = validate_for_fulfillment(
        {"product_type": "print", "print_quality": "approve",
         "sale_price": 100.0, "gelato_cost": 10.0}, GOOD_ADDR, "uid", "https://x/y.png")
    assert good["ok"], good["issues"]


def test_below_floor_override_allows_loss_leader(monkeypatch):
    # The escape hatch: deliberate loss-leaders pass when explicitly allowed.
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "ALLOW_BELOW_FLOOR_ORDERS", True, raising=False)
    from quoteforge.automation.pipeline_orchestrator import validate_for_fulfillment
    r = validate_for_fulfillment(
        {"product_type": "print", "print_quality": "approve",
         "sale_price": 10.0, "gelato_cost": 9.0}, GOOD_ADDR, "uid", "https://x/y.png")
    assert r["ok"], r["issues"]


# ── #3: wall-art orders resolve a gelato_cost so the margin gate can fire ─────
def test_wallart_cost_resolves_for_margin_check():
    # REGRESSION: wall art carried no gelato_cost, so the margin check never fired
    # for the shop's primary product line.
    from quoteforge.etsy.variations import build_variations, wallart_cost_for
    v = build_variations()[0]
    label = {"poster": "Poster", "framed": "Framed", "canvas": "Canvas",
             "acrylic": "Acrylic", "metal": "Metal"}[v.material]
    if v.material == "framed":
        label = f"Framed - {v.frame_color}"
    cost = wallart_cost_for(label, v.size)
    assert cost is not None and cost > 0
    assert wallart_cost_for("not a real material", "99x99") is None


# ── #9: duplicate confirm of the same basket dedups to one order ─────────────
def test_same_basket_dedups_to_one_order(tmp_path, monkeypatch):
    # REGRESSION: the order id keyed on design_id='cart-'+Date.now() (unique every
    # click), so a refresh/resubmit created a duplicate WEB- order.
    _db(tmp_path, monkeypatch)
    from quoteforge.automation.design_confirm import _intake_order
    contact = {"name": "Ann", "addr": "1 St, Atlanta GA 30301",
               "country": "US", "state": "GA"}
    money = {"sale_price": 42.0, "item_count": 2, "line_items": '[{"t":"mug"}]'}
    a, a_created = _intake_order("b@x.com", "cart-111", contact, money)
    b, b_created = _intake_order("b@x.com", "cart-222", contact, money)  # same basket
    assert a and a == b                       # same order id (deduped)
    assert a_created and not b_created         # first creates; the duplicate does not


# ── #8b: an accepted design is immutable (no silent post-approval swap) ───────
def test_accepted_design_cannot_be_overwritten(tmp_path, monkeypatch):
    # REGRESSION: save_design overwrote unconditionally, so the approved design
    # could be swapped after the customer authorized it.
    db = _db(tmp_path, monkeypatch)
    db.save_design("b@x.com", design_json='{"v":1}', design_id="d1")
    db.accept_design("b@x.com", "d1")
    db.save_design("b@x.com", design_json='{"v":2}', design_id="d1")   # must be blocked
    d = next(x for x in db.get_designs("b@x.com") if x["design_id"] == "d1")
    assert '"v":1' in d["design_json"].replace(" ", "")


# ── #7: dynamic variant resolution is apparel-only (non-apparel -> manual) ────
def test_nonapparel_variant_resolution_falls_to_manual(monkeypatch):
    # REGRESSION: the resolver fired apparel GarmentColor/GarmentSize attributes
    # for every family; for mug/branded/calendar it can't match and must fall to
    # manual (static per-SKU UID), not silently imply it auto-resolves.
    import quoteforge.automation.gelato_variant_resolver as r
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False, raising=False)
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "k",
                        raising=False)
    monkeypatch.setattr(r, "_uid_map", lambda: {}, raising=False)
    monkeypatch.setattr(r, "_family_value", lambda gid: "real-branded-family",
                        raising=False)

    def _boom(*a, **k):
        raise AssertionError("apparel search must NOT run for a branded product")
    monkeypatch.setattr(r, "_gelato_search_variant", _boom, raising=False)
    # 'tote' is branded (get_garment returns None) -> guard returns None, no search.
    assert r.resolve_variant_uid("BR-SKU", garment_id="tote",
                                 color="Natural", size="One Size") is None


# ── #2: phone case is not sellable (no model capture) ────────────────────────
def test_phonecase_not_sellable_and_not_routable():
    # REGRESSION: a phone case offered only iPhone/Samsung (no model), so it could
    # never be produced correctly; it must be hidden + never resolve a routing SKU.
    from quoteforge.etsy.branded_catalog import branded_sellable, branded_sku_for
    assert branded_sellable("phonecase") is False
    assert branded_sellable("tote") is True
    assert branded_sku_for("phonecase", "iPhone", "White") is None
    assert branded_sku_for("tote", "One Size", "Natural") is not None


def test_phonecase_absent_from_storefront():
    # The unfulfillable product must not render anywhere customer-facing.
    src = Path(__file__).resolve().parents[1] / "quoteforge" / "docs" / "index.html"
    if not src.exists():
        src = Path(__file__).resolve().parents[1] / "docs" / "index.html"
    if src.exists():
        assert "phone case" not in src.read_text(encoding="utf-8").lower()


# ── #5/#6: apparel supplier photos are re-hosted same-origin (no leak/taint) ──
def test_apparel_photos_routed_through_rehost():
    # REGRESSION: apparel photos were injected as RAW Gelato URLs (supplier leak +
    # canvas taint); they must go through _emit_url to be re-hosted same-origin.
    src = (Path(__file__).resolve().parents[1] / "quoteforge" / "etsy"
           / "listing_preview.py").read_text(encoding="utf-8")
    assert "def _emit_url(" in src
    assert "_emit_url(_url, f\"tile-{_gidk}.jpg\")" in src
    assert "_garment_photos[_gidk] = _url" not in src   # the raw-URL leak is gone


# ── #10: concurrent duplicate routing submits to the vendor only once ────────
def test_concurrent_duplicate_routing_submits_once(tmp_path, monkeypatch):
    # REGRESSION: two duplicate webhooks (each a thread) could both pass the
    # vendor_order_id idempotency check and double-submit. The per-order lock
    # serializes routing so only one submission happens.
    import threading
    import time
    db = _db(tmp_path, monkeypatch)
    db.create_order({"order_id": "QF-R", "customer_email": "b@x.com",
                     "recipient_name": "Ann", "occasion": "Birthday"})
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False, raising=False)
    calls = []

    def _slow_create(order_id, recipient, artwork_url, product_uid):
        calls.append(order_id)
        time.sleep(0.15)                      # widen the race window
        db.update_order(order_id, vendor_order_id="VID-1")
        return {"id": "VID-1"}
    import quoteforge.fulfillment.router as router
    monkeypatch.setattr("quoteforge.automation.gelato_api.create_gelato_order",
                        _slow_create, raising=False)
    order = {"order_id": "QF-R", "vendor": "gelato", "gelato_product_uid": "uid-real",
             "product_type": "print"}
    results = []

    def _go():
        results.append(router.route_order(order, recipient=GOOD_ADDR,
                                          artwork_url="https://x/y.png"))
    ts = [threading.Thread(target=_go) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(calls) == 1, f"vendor submitted {len(calls)} times (must be 1)"
    assert sum(1 for r in results if r["status"] == "submitted") == 1
    assert sum(1 for r in results if r["status"] == "duplicate") == 1
