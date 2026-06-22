from quoteforge.etsy.calendar_catalog import (
    CALENDAR_CATALOG, build_calendar_variations, calendar_dimensions_for, get_calendar)


def test_catalog_has_core_calendars():
    ids = {p.product_id for p in CALENDAR_CATALOG}
    for pid in ("wall_cal", "desk_cal", "family_cal", "corporate_cal",
                "photo_cal", "event_cal", "promo_cal"):
        assert pid in ids, pid


def test_every_variant_clears_the_margin_floor():
    from quoteforge.config import TARGET_MARGIN_PCT
    vs = build_calendar_variations()
    assert vs
    for v in vs:
        assert v.price > v.gelato_cost
        assert v.margin_pct >= TARGET_MARGIN_PCT


def test_dimensions_lookup_falls_back_safely():
    assert calendar_dimensions_for("wall_cal")[0] > 0
    assert calendar_dimensions_for("nope")[0] > 0


def test_parse_and_resolve_sku_round_trip():
    from quoteforge.etsy.calendar_catalog import parse_calendar_format, resolve_calendar_sku
    assert parse_calendar_format("Wall Calendar - White") == ("wall_cal", "White")
    assert parse_calendar_format("Framed - Oak") == (None, None)
    assert resolve_calendar_sku("Wall Calendar - White", "A3") == "GEL-WALL_CAL-A3-WHITE"
    assert resolve_calendar_sku("Wall Calendar - White", "BadSize") is None


def test_enrich_calendar_order_merges_fields_or_empty():
    from quoteforge.etsy.calendar_catalog import enrich_calendar_order
    out = enrich_calendar_order({"material": "Wall Calendar - White", "size": "A3"})
    assert out["product_type"] == "calendar" and out["product_id"] == "wall_cal"
    assert out["color"] == "White" and out["gelato_sku"] == "GEL-WALL_CAL-A3-WHITE"
    assert out["gelato_cost"] > 0
    assert enrich_calendar_order({"material": "Framed - Oak"}) == {}


def test_pipeline_and_webhook_call_calendar_enrich():
    import quoteforge.automation.pipeline_orchestrator as po, quoteforge.automation.webhook_server as ws, inspect
    assert "enrich_calendar_order" in inspect.getsource(po)
    assert "enrich_calendar_order" in inspect.getsource(ws)


def test_verify_calendar_mappings_reports_placeholders():
    from quoteforge.etsy.calendar_catalog import verify_calendar_mappings
    rep = verify_calendar_mappings()
    assert rep["total"] > 0
    assert set(("total", "configured", "placeholder_count", "placeholders", "all_real")) <= set(rep)


def test_margin_guard_includes_calendars():
    from quoteforge.etsy.margin_guard import audit_catalog
    assert any(r.get("kind") == "calendar" for r in audit_catalog()["rows"])
