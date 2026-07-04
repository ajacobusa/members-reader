"""Operationalization: an apparel order flows through the live pipeline.

Covers the ingest seam (format -> product_type/garment/colour + resolved Gelato
apparel UID), UID resolution (placeholder vs real), the colour proof-lock, and
the sync/go-live guard coverage. Wall-art behaviour must be untouched throughout.
"""
import json

import pytest

from quoteforge.etsy import apparel_catalog as A


# ── Ingest enrichment (the single seam) ──────────────────────────

def test_enrich_apparel_order_sets_product_type_and_colour():
    # REGRESSION: an apparel basket line is turned into structured fields the
    # pipeline + reporting use; colour is no longer trapped inside the format.
    out = A.enrich_apparel_order({"material": "Men's T-Shirt - Black", "product_size": "M"})
    assert out["product_type"] == "apparel"
    assert out["garment_id"] == "m_tshirt"
    assert out["color"] == "Black"
    assert out["gelato_sku"] == "GEL-M-TSHIRT-M-BLACK"


def test_enrich_is_noop_for_wall_art():
    # REGRESSION: wall art must be completely unaffected - enrichment returns {}.
    assert A.enrich_apparel_order({"material": "Framed - Premium Solid Oak",
                                   "size": "18x24 in"}) == {}
    assert A.enrich_apparel_order({"material": "Poster (unframed)", "size": "18x24"}) == {}


def test_webhook_build_order_data_enriches_apparel():
    # REGRESSION: the real ingest choke point wires the enrichment.
    from quoteforge.automation.webhook_server import _build_order_data
    od = _build_order_data(
        {"recipient_name": "Sam", "occasion": "Birthday",
         "material": "Men's Hoodie - Navy", "size": "XL"}, "E1")
    assert od["product_type"] == "apparel"
    assert od["color"] == "Navy" and od["garment_id"] == "m_hoodie"


def test_webhook_build_order_data_leaves_wall_art_alone():
    from quoteforge.automation.webhook_server import _build_order_data
    od = _build_order_data(
        {"recipient_name": "Sam", "occasion": "Birthday",
         "material": "Framed - Slim Black", "size": "11x14 in"}, "E2")
    assert od.get("product_type") in (None, "print", "")  # not flipped to apparel
    assert "garment_id" not in od


# ── UID resolution (placeholder vs real) ─────────────────────────

def test_unmapped_or_placeholder_uid_resolves_to_none(monkeypatch):
    # No map -> None (routes to manual, never ships a placeholder).
    monkeypatch.delenv("GELATO_UID_MAP", raising=False)
    assert A.resolve_apparel_uid("GEL-M-TSHIRT-M-BLACK") is None
    # A map that still points at a GEL-* placeholder is also rejected.
    monkeypatch.setenv("GELATO_UID_MAP",
                       json.dumps({"GEL-M-TSHIRT-M-BLACK": "GEL-STILL-PLACEHOLDER"}))
    assert A.resolve_apparel_uid("GEL-M-TSHIRT-M-BLACK") is None


def test_real_uid_resolves_and_enriches(monkeypatch):
    monkeypatch.setenv("GELATO_UID_MAP",
                       json.dumps({"GEL-M-TSHIRT-M-BLACK": "apparel_real_uid_123"}))
    assert A.resolve_apparel_uid("GEL-M-TSHIRT-M-BLACK") == "apparel_real_uid_123"
    out = A.enrich_apparel_order({"material": "Men's T-Shirt - Black", "size": "M"})
    assert out["gelato_product_uid"] == "apparel_real_uid_123"


# ── Colour is part of the locked proof ───────────────────────────

def test_color_is_locked_after_proof_approval(tmp_path, monkeypatch):
    # REGRESSION: once the apparel proof is approved, colour is immutable like
    # size/material - an approved Black tee can't silently become Navy.
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.DB_PATH", tmp_path / "t.db", raising=False)
    import importlib
    from quoteforge.db import database as db
    importlib.reload(db)
    db.init_db()
    db.create_order({"order_id": "AP1", "recipient_name": "X", "occasion": "Y",
                     "color": "Black"})
    db.update_order("AP1", proof_approved=1)
    with pytest.raises(db.OrderLockedError):
        db.update_order("AP1", color="Navy")
    # re-writing the same colour is a no-op (allowed)
    db.update_order("AP1", color="Black")


# ── Sync + go-live guard cover apparel ───────────────────────────

def test_gelato_sync_includes_apparel_skus():
    # REGRESSION: apparel availability/cost syncs and apparel placeholders are
    # surfaced by the same guard as print products.
    from quoteforge.automation.gelato_sync import _all_skus
    skus = set(_all_skus())
    assert "GEL-M-TSHIRT-M-BLACK" in skus
    assert any(s.startswith("GEL-M-HOODIE-") for s in skus)


def test_sync_text_warns_on_apparel_placeholders(monkeypatch):
    # In TEST_MODE the sync is a no-op but still reports placeholders; apparel
    # seed UIDs must be counted so they can't silently ship.
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.automation import gelato_sync
    r = gelato_sync.sync_catalog()
    assert r["placeholder_uids"] >= 75      # all apparel variants are placeholders


# ── Financial accuracy: true garment cost flows off the order ─────

def test_enrich_sets_true_garment_cost():
    # REGRESSION: financials/margin read order['gelato_cost'] directly; apparel
    # must carry the real garment cost incl. the 2XL upcharge (13 + 2 = 15), so
    # no downstream module needs apparel special-casing.
    out = A.enrich_apparel_order({"material": "Men's T-Shirt - Black", "size": "2XL"})
    assert out["gelato_cost"] == 15.0
    base = A.enrich_apparel_order({"material": "Men's T-Shirt - Black", "size": "M"})
    assert base["gelato_cost"] == 13.0


# ── Claims safety: wrong size is customer-fault, never auto-reprinted ──

def test_wrong_size_is_customer_fault_no_cover():
    # REGRESSION: "too small"/"doesn't fit" must classify as a customer-fault,
    # NOT-covered issue - declined, never a free reprint/refund.
    from quoteforge.etsy.resolution import resolve_issue
    for phrase in ("too small", "doesn't fit", "wrong size"):
        r = resolve_issue(phrase)
        assert r["recognized"] and r["category"] == "wrong_size"
        assert r["fault"] == "customer"
        assert r["gelato_covered"] is False


def test_claim_form_has_apparel_sizing_and_it_is_not_covered():
    from quoteforge.fulfillment.claim_service import ISSUE_TYPES, _COVERED
    assert ISSUE_TYPES.get("Apparel sizing / fit") == "wrong_size"
    assert "wrong_size" not in _COVERED      # never an auto free reprint


# ── Customer copy generalized for apparel ────────────────────────

def test_messages_generalized_not_print_specific():
    from quoteforge.etsy.customer_messages import BASE_TEMPLATES
    blob = " ".join(BASE_TEMPLATES.values())
    assert "this print brings joy" not in blob
    assert "personalized print arrived" not in blob
    assert "your personalized item" in blob   # generalized wording present
    # supplier euphemism is fine; the real supplier name is not
    assert "gelato" not in blob.lower()


# ── Apparel folded into reporting + support surfaces ─────────────

def test_margin_audit_includes_apparel():
    # REGRESSION: the catalog margin audit covers apparel variants (was print-only).
    from quoteforge.etsy.margin_guard import audit_catalog
    rows = audit_catalog()["rows"]
    appa = [r for r in rows if r["kind"] == "apparel"]
    assert appa and all(r["ok"] for r in appa)   # apparel present + clears floor


def test_apparel_cost_override_reprices_and_holds_floor(tmp_path, monkeypatch):
    # REGRESSION: a live Gelato cost increase reprices apparel UP and still clears
    # the 60% floor - the same auto-reprice the print catalog gets (was untested).
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge.etsy.catalog_state import save_state
    from quoteforge.config import TARGET_MARGIN_PCT
    sku = "GEL-M-TSHIRT-M-WHITE"
    base = next(v for v in A.build_apparel_variations() if v.gelato_sku == sku)
    save_state({sku: {"available": True, "cost": 25.0}})       # cost jumps 13 -> 25
    hi = next(v for v in A.build_apparel_variations() if v.gelato_sku == sku)
    assert hi.gelato_cost == 25.0
    assert hi.price > base.price                               # repriced up
    assert hi.margin_pct >= TARGET_MARGIN_PCT                  # still clears floor


def test_router_never_submits_placeholder_uid():
    # REGRESSION: a GEL-* placeholder UID routes to manual, never to production.
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "PH1", "gelato_product_uid": "GEL-M-TSHIRT-M-WHITE",
                     "vendor": "gelato"},
                    recipient={"name": "A", "address": "1 St", "city": "X",
                               "postCode": "1", "country": "US"},
                    artwork_url="http://x/a.png")
    assert r["status"] == "manual"
    assert "placeholder" in r["detail"].lower()


def test_ange_kb_answers_apparel_sizing():
    # REGRESSION: the storefront assistant can answer apparel fit without leaking.
    from quoteforge.ai.ange import KB
    hits = [a for (kw, q, a) in KB if "hoodie" in kw or "apparel" in kw]
    assert hits
    a = hits[0].lower()
    assert "final" in a and "fit" in a
    assert "gelato" not in a and "printify" not in a


# ── Etsy apparel inventory: one listing per garment, Size x Colour ──

def test_apparel_inventory_payload_two_axes_priced():
    # REGRESSION: each garment is a Size x Colour Etsy listing (the 2-axis limit),
    # every offering priced > 0, no supplier name in the payload.
    from quoteforge.automation.etsy_publisher import (
        build_apparel_inventory_payload, apparel_listing_garments)
    import json
    garments = apparel_listing_garments()
    assert set(garments) >= {"m_tshirt", "w_tshirt", "m_hoodie", "w_hoodie"}
    p = build_apparel_inventory_payload("m_tshirt")
    g = A.get_garment("m_tshirt")
    assert len(p["products"]) == len(g.sizes) * len(g.colors)   # full grid
    assert p["price_on_property"] == [513, 514]                 # exactly two axes
    for prod in p["products"]:
        assert len(prod["property_values"]) == 2                # Size + Color only
        names = {pv["property_name"] for pv in prod["property_values"]}
        assert names == {"Size", "Color"}
        assert prod["offerings"][0]["price"] > 0
    assert "gelato" not in json.dumps(p).lower().replace("gel-", "")  # no supplier name


def test_apparel_without_faithful_artwork_is_held_for_manual(tmp_path, monkeypatch):
    # REGRESSION (print-fidelity audit): the storefront apparel design (photo/wording/
    # template/position/rotation) is NOT yet rendered into the print file - the pipeline
    # substitutes a generic poster (render_local_poster), so "what the buyer approved" is
    # not "what would print". An apparel order must therefore NEVER auto-submit that poster;
    # it is HELD for manual until a faithful per-side print file (extra_files) or an explicit
    # faithful_artwork flag is present. Guards preview!=print from shipping at go-live.
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.GELATO_FULFILLMENT_MODE", "api", raising=False)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.db import database as db
    db.init_db()
    from quoteforge.fulfillment.router import _route_order_impl
    rec = {"name": "Sam", "address1": "1 St", "city": "NYC", "state": "NY",
           "postal_code": "10001", "country": "US"}
    held = _route_order_impl({"order_id": "", "product_type": "apparel", "vendor": "gelato",
                              "gelato_product_uid": "uid-x"},
                             recipient=rec, artwork_url="https://x/y.png")
    assert held["status"] == "manual" and "not yet rendered" in held["detail"]  # poster NOT auto-submitted
    # With a faithful print file the preview!=print guard is satisfied - BUT the #167
    # calibration gate still HOLDS it for manual until the owner signs off a test print,
    # so a mis-calibrated mapping can't auto-print on real garments.
    held2 = _route_order_impl({"order_id": "", "product_type": "apparel", "vendor": "gelato",
                               "gelato_product_uid": "uid-x", "faithful_artwork": True},
                              recipient=rec, artwork_url="https://x/y.png")
    assert held2["status"] == "manual" and "calibration" in held2["detail"]
    # ...and once the owner has calibrated (a good test print), the calibration gate no
    # longer force-holds (the order may still hold for unrelated reasons, but NOT for
    # calibration - that specific block is released).
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", True, raising=False)
    ok = _route_order_impl({"order_id": "", "product_type": "apparel", "vendor": "gelato",
                            "gelato_product_uid": "uid-x", "faithful_artwork": True},
                           recipient=rec, artwork_url="https://x/y.png")
    assert not (ok["status"] == "manual" and "calibration" in ok.get("detail", ""))


# ── End-to-end: an apparel order through the live pipeline ────────

def test_apparel_order_through_pipeline(tmp_path, monkeypatch):
    # REGRESSION: a direct apparel order is enriched (product_type/colour/cost),
    # persisted, and does NOT get a wall-art room mockup. Proves the pipeline is
    # apparel-aware regardless of ingest path.
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.GENERATE_ROOM_MOCKUP", True, raising=False)
    from quoteforge.db import database as db
    db.init_db()
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline
    run_full_pipeline({"order_id": "APX", "etsy_order_id": "APX",
                       "recipient_name": "Sam", "occasion": "Birthday",
                       "material": "Men's T-Shirt - Black", "product_size": "M"},
                      skip_proof=True)
    o = db.get_order("APX")
    assert o["product_type"] == "apparel"
    assert o["color"] == "Black"
    assert o["gelato_cost"] == 13.0          # true garment cost on the order
    assert not o.get("mockup_url")           # no room mockup for apparel


def test_pipeline_threads_product_type_into_route_order(tmp_path, monkeypatch):
    # REGRESSION (#167): route_order is a thin wrapper that does NOT enrich product_type
    # from the DB, so its apparel/calendar safety HOLDS silently no-op'd on the auto-
    # pipeline path when the routing dict omitted product_type. Pin that the pipeline now
    # threads product_type through, so those holds actually protect auto-routed orders.
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    seen = {}
    import quoteforge.fulfillment.router as router
    import quoteforge.automation.pipeline_orchestrator as po

    def _spy(order, recipient=None, artwork_url=""):
        seen["product_type"] = order.get("product_type")
        return {"status": "native", "vendor": "gelato-native", "id": "", "detail": "spy"}
    monkeypatch.setattr(router, "route_order", _spy)
    # pass the pre-routing validation gate so the order reaches route_order
    monkeypatch.setattr(po, "validate_for_fulfillment",
                        lambda *a, **k: {"ok": True, "issues": []})
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline
    run_full_pipeline({"order_id": "APY", "etsy_order_id": "APY",
                       "recipient_name": "Sam", "occasion": "Birthday",
                       "material": "Men's T-Shirt - Black", "product_size": "M",
                       "recipient_address": {"name": "Sam", "address1": "1 St",
                                             "city": "NYC", "state": "NY",
                                             "postal_code": "10001", "country": "US"}},
                      skip_proof=True)
    assert seen.get("product_type") == "apparel"   # the gate can now see it
