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
