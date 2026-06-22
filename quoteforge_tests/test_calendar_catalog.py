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
