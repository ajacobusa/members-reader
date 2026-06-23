"""Wall-Art -> real Gelato UID mapping (network injected for tests)."""

from quoteforge.automation.gelato_wallart_map import (
    build_wallart_map, pick_wallart_uid)


class _P:
    def __init__(self, category, size, sku, pid):
        self.category, self.size, self.gelato_sku, self.product_id = (
            category, size, sku, pid)


def test_pick_prefers_portrait_keywords_and_plain_finish():
    uids = ["flat_8x10_uncoated_4-0_hor",
            "flat_8x10_170-gsm-coated-silk_4-0_ver",
            "metallic_8x10_3-mm-silver-brushed-grain_4-0_ver"]
    # most keyword hits + _ver + not brushed
    assert pick_wallart_uid(uids, ("coated-silk", "170-gsm")) == \
        "flat_8x10_170-gsm-coated-silk_4-0_ver"


def test_pick_avoids_brushed_when_plain_available():
    uids = ["metallic_3-mm-brushed_4-0_ver", "metallic_3-mm_4-0_ver"]
    assert pick_wallart_uid(uids, ("3-mm",)) == "metallic_3-mm_4-0_ver"


def test_build_maps_each_category_with_real_returned_uids():
    cat = [_P("poster", "8x10 in", "GEL-POSTER-8X10-STD", "poster_8x10"),
           _P("canvas", "11x14 in", "GEL-CANVAS-11X14-PRM", "canvas_11x14"),
           _P("acrylic", "12x16 in", "GEL-ACRYLIC-12X16-ULT", "acrylic_12x16")]

    def fake_fetch(catalog, size_attr, token):
        # echo a plausible real-looking UID for the requested catalog+size
        return [f"{catalog}_{token}_default_4-0_ver"]

    res = build_wallart_map(fake_fetch, catalog_iter=cat)
    assert res["mapped_count"] == 3 and res["total"] == 3
    assert res["map"]["GEL-POSTER-8X10-STD"].startswith("posters_8x10")
    # never invents a UID - only what fetch returned
    assert all("_ver" in v for v in res["map"].values())


def test_unavailable_size_is_flagged_not_invented():
    cat = [_P("metal", "8x10 in", "GEL-METAL-8X10-ULT", "metal_8x10")]
    res = build_wallart_map(lambda c, a, t: [], catalog_iter=cat)  # Gelato has no 8x10
    assert res["mapped_count"] == 0
    assert "GEL-METAL-8X10-ULT" in res["unmapped"]
    assert res["map"] == {}
