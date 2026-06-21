from quoteforge.etsy.mug_catalog import (
    MUG_CATALOG, build_mug_variations, mug_dimensions_for, get_mug)


def test_catalog_has_core_mugs():
    ids = {p.product_id for p in MUG_CATALOG}
    for pid in ("classic_mug", "large_mug", "color_mug", "accent_mug",
                "enamel_mug", "travel_mug", "xl_mug"):
        assert pid in ids, pid


def test_every_variant_clears_the_margin_floor():
    from quoteforge.config import TARGET_MARGIN_PCT
    vs = build_mug_variations()
    assert vs
    for v in vs:
        assert v.price > v.gelato_cost
        assert v.margin_pct >= TARGET_MARGIN_PCT


def test_dimensions_lookup_falls_back_safely():
    assert mug_dimensions_for("classic_mug")[0] > 0
    assert mug_dimensions_for("nope")[0] > 0


def test_parse_and_resolve_sku_round_trip():
    from quoteforge.etsy.mug_catalog import parse_mug_format, resolve_mug_sku
    assert parse_mug_format("Classic Ceramic Mug (11oz) - White") == ("classic_mug", "White")
    assert parse_mug_format("Framed - Oak") == (None, None)
    assert resolve_mug_sku("Classic Ceramic Mug (11oz) - White", "11oz") == "GEL-CLASSIC_MUG-11OZ-WHITE"
    assert resolve_mug_sku("Classic Ceramic Mug (11oz) - White", "BadSize") is None


def test_enrich_mug_order_merges_fields_or_empty():
    from quoteforge.etsy.mug_catalog import enrich_mug_order
    out = enrich_mug_order({"material": "Classic Ceramic Mug (11oz) - White", "size": "11oz"})
    assert out["product_type"] == "mug" and out["product_id"] == "classic_mug"
    assert out["color"] == "White" and out["gelato_sku"] == "GEL-CLASSIC_MUG-11OZ-WHITE"
    assert out["gelato_cost"] > 0
    assert enrich_mug_order({"material": "Framed - Oak"}) == {}


def test_verify_mug_mappings_reports_placeholders():
    from quoteforge.etsy.mug_catalog import verify_mug_mappings
    rep = verify_mug_mappings()
    assert rep["total"] > 0
    assert set(("total", "configured", "placeholder_count", "placeholders", "all_real")) <= set(rep)


def test_pipeline_and_webhook_call_mug_enrich():
    import quoteforge.automation.pipeline_orchestrator as po, quoteforge.automation.webhook_server as ws, inspect
    assert "enrich_mug_order" in inspect.getsource(po)
    assert "enrich_mug_order" in inspect.getsource(ws)
