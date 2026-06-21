from quoteforge.etsy.branded_catalog import (
    BRANDED_CATALOG, build_branded_variations, branded_dimensions_for, get_product)


def test_catalog_has_core_products():
    ids = {p.product_id for p in BRANDED_CATALOG}
    for pid in ("tote", "bottle", "tumbler", "mousepad", "notebook",
                "journal", "sticker", "phonecase", "keychain"):
        assert pid in ids, pid


def test_every_variant_clears_the_margin_floor():
    from quoteforge.config import TARGET_MARGIN_PCT
    vs = build_branded_variations()
    assert vs, "no variants built"
    for v in vs:
        assert v.price > v.gelato_cost
        assert v.margin_pct >= TARGET_MARGIN_PCT


def test_dimensions_lookup_falls_back_safely():
    assert branded_dimensions_for("tote")[0] > 0
    assert branded_dimensions_for("does-not-exist")[0] > 0


def test_parse_and_resolve_sku_round_trip():
    from quoteforge.etsy.branded_catalog import parse_branded_format, resolve_branded_sku
    assert parse_branded_format("Organic Cotton Tote Bag - Natural") == ("tote", "Natural")
    assert parse_branded_format("Framed - Oak") == (None, None)
    assert resolve_branded_sku("Organic Cotton Tote Bag - Natural", "One Size") == "GEL-TOTE-ONE-SIZE-NATURAL"
    assert resolve_branded_sku("Organic Cotton Tote Bag - Natural", "BadSize") is None


def test_enrich_branded_order_merges_fields_or_empty():
    from quoteforge.etsy.branded_catalog import enrich_branded_order
    out = enrich_branded_order({"material": "Organic Cotton Tote Bag - Natural", "size": "One Size"})
    assert out["product_type"] == "branded" and out["product_id"] == "tote"
    assert out["color"] == "Natural" and out["gelato_sku"] == "GEL-TOTE-ONE-SIZE-NATURAL"
    assert out["gelato_cost"] > 0
    assert enrich_branded_order({"material": "Framed - Oak"}) == {}


def test_pipeline_and_webhook_call_branded_enrich():
    import quoteforge.automation.pipeline_orchestrator as po
    import quoteforge.automation.webhook_server as ws
    import inspect
    assert "enrich_branded_order" in inspect.getsource(po)
    assert "enrich_branded_order" in inspect.getsource(ws)


def test_verify_branded_mappings_reports_placeholders():
    from quoteforge.etsy.branded_catalog import verify_branded_mappings
    rep = verify_branded_mappings()
    assert rep["total"] > 0
    assert set(("total", "configured", "placeholder_count", "placeholders", "all_real")) <= set(rep)


def test_margin_guard_includes_branded():
    from quoteforge.etsy.margin_guard import audit_catalog
    rows = audit_catalog()["rows"]
    assert any(r.get("kind") == "branded" for r in rows), "branded not in margin audit"


def test_catalog_sync_baseline_includes_branded():
    from quoteforge.automation.catalog_sync import build_local_catalog
    records = build_local_catalog()
    assert any(r.get("type") == "branded" or pid in {p.product_id for p in BRANDED_CATALOG}
               for pid, r in records.items()), "branded not in local catalog baseline"
