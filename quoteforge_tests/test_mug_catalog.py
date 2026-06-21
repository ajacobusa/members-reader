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
