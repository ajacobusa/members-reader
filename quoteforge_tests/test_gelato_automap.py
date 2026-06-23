"""Auto-mapping product families to real Gelato UIDs (network injected for tests)."""


def test_automap_maps_all_fulfillable_and_flags_the_rest():
    from quoteforge.automation.gelato_automap import build_family_map, FAMILY_PLAN

    def fake_fetch(cat):
        return [{"productUid": f"{cat}_product_classic_premium_economy_white_11-oz_"
                               f"ceramic_stainless_unisex_crewneck_tote_iphone_notebook"}]

    res = build_family_map(fake_fetch)
    fulfillable = sum(1 for c, _ in FAMILY_PLAN.values() if c)
    assert res["mapped_count"] == fulfillable
    # the 3 catalog-less families are flagged and never mapped to a fake/placeholder
    for f in ("branded:sticker", "branded:keychain", "branded:mousepad"):
        assert f in res["unmapped"]
        assert f not in res["map"]
    # never emits a GEL-* placeholder
    assert all(not v.upper().startswith("GEL-") for v in res["map"].values())


def test_automap_prefers_keyword_match_over_first():
    from quoteforge.automation.gelato_automap import pick_uid
    prods = [{"productUid": "mug_first_black_15-oz"},
             {"productUid": "mug_ceramic_11-oz_white"}]
    assert pick_uid(prods, ("ceramic", "11-oz", "white")) == "mug_ceramic_11-oz_white"


def test_automap_falls_back_to_first_when_no_keyword_hit():
    from quoteforge.automation.gelato_automap import pick_uid
    prods = [{"productUid": "abc"}, {"productUid": "def"}]
    assert pick_uid(prods, ("zzz",)) == "abc"
