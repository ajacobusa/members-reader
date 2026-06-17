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
    out = A.enrich_apparel_order({"material": "T-Shirt - Black", "product_size": "M"})
    assert out["product_type"] == "apparel"
    assert out["garment_id"] == "tshirt"
    assert out["color"] == "Black"
    assert out["gelato_sku"] == "GEL-TSHIRT-M-BLACK"


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
         "material": "Hoodie - Navy", "size": "XL"}, "E1")
    assert od["product_type"] == "apparel"
    assert od["color"] == "Navy" and od["garment_id"] == "hoodie"


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
    assert A.resolve_apparel_uid("GEL-TSHIRT-M-BLACK") is None
    # A map that still points at a GEL-* placeholder is also rejected.
    monkeypatch.setenv("GELATO_UID_MAP",
                       json.dumps({"GEL-TSHIRT-M-BLACK": "GEL-STILL-PLACEHOLDER"}))
    assert A.resolve_apparel_uid("GEL-TSHIRT-M-BLACK") is None


def test_real_uid_resolves_and_enriches(monkeypatch):
    monkeypatch.setenv("GELATO_UID_MAP",
                       json.dumps({"GEL-TSHIRT-M-BLACK": "apparel_real_uid_123"}))
    assert A.resolve_apparel_uid("GEL-TSHIRT-M-BLACK") == "apparel_real_uid_123"
    out = A.enrich_apparel_order({"material": "T-Shirt - Black", "size": "M"})
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
    assert "GEL-TSHIRT-M-BLACK" in skus
    assert any(s.startswith("GEL-HOODIE-") for s in skus)


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
    out = A.enrich_apparel_order({"material": "T-Shirt - Black", "size": "2XL"})
    assert out["gelato_cost"] == 15.0
    base = A.enrich_apparel_order({"material": "T-Shirt - Black", "size": "M"})
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
    assert set(garments) >= {"tshirt", "hoodie", "sweatshirt"}
    p = build_apparel_inventory_payload("tshirt")
    g = A.get_garment("tshirt")
    assert len(p["products"]) == len(g.sizes) * len(g.colors)   # full grid
    assert p["price_on_property"] == [513, 514]                 # exactly two axes
    for prod in p["products"]:
        assert len(prod["property_values"]) == 2                # Size + Color only
        names = {pv["property_name"] for pv in prod["property_values"]}
        assert names == {"Size", "Color"}
        assert prod["offerings"][0]["price"] > 0
    assert "gelato" not in json.dumps(p).lower().replace("gel-", "")  # no supplier name


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
                       "material": "T-Shirt - Black", "product_size": "M"},
                      skip_proof=True)
    o = db.get_order("APX")
    assert o["product_type"] == "apparel"
    assert o["color"] == "Black"
    assert o["gelato_cost"] == 13.0          # true garment cost on the order
    assert not o.get("mockup_url")           # no room mockup for apparel
