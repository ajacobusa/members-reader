"""Resolver hard discriminators - lessons from the FIRST live dry-run (hoodies,
2026-07-11), whose top matches were all wrong at conf 0.8 (>= the 0.72 write
threshold): a men's royal-blue hoodie matched a KIDS hoodie in CAROLINA-BLUE,
and women's SKUs matched a cropped TriDri / kids Gildan. Size was already a
hard dimension; colour and cut were only soft token hits, and the blank brand
was ignored. These would have become 5,000+ garbage drafts for the reviewer.

Hard rules pinned here:
  1. COLOUR is a dimension: every (post-alias) colour token of our SKU must be
     positively present - 'blue' alone never claims 'carolina-blue'.
  2. CUT: an adult SKU (GEL-M-* / GEL-W-*) is DISQUALIFIED from kids/baby cuts.
  3. BRAND tie-break: among survivors, the product naming our garment's actual
     blank (e.g. lane-seven ls14001) wins over an equal-confidence stranger.
"""
from quoteforge.automation.gelato_uid_resolver import _sku_tokens, resolve_sku


def _p(uid, color, size, extra="", cut="mens"):
    return {"uid": uid,
            "text": f"hoodie {color} {size} {extra}",
            "attrs": {"GarmentColor": color, "GarmentSize": size,
                      "GarmentCut": cut, "GarmentCategory": "hoodie"}}


def _item(sku):
    return {"family": "apparel", "sku": sku,
            "tokens": _sku_tokens("apparel", sku)}


def test_partial_colour_token_never_matches():
    # REGRESSION (dry-run finding 1): ROYAL-BLUE must not resolve to a product
    # whose colour is carolina-blue just because 'blue' appears.
    wrong = _p("apparel_..._gco_carolina-blue_gsi_m", "carolina-blue", "m")
    r = resolve_sku(_item("GEL-M-HOODIE-M-ROYAL-BLUE"), [wrong])
    assert r["uid"] is None, r
    right = _p("apparel_..._gco_royal-blue_gsi_m", "royal-blue", "m")
    r = resolve_sku(_item("GEL-M-HOODIE-M-ROYAL-BLUE"), [wrong, right])
    assert r["uid"] == right["uid"], r


def test_adult_sku_disqualified_from_kids_and_baby_cuts():
    # REGRESSION (dry-run finding 2): a men's/women's SKU must never claim a
    # kids or baby product, whatever the token overlap.
    kids = _p("apparel_..._gcu_kids_gco_sand_gsi_xs", "sand", "xs", cut="kids")
    baby = _p("apparel_..._gcu_baby_gco_sand_gsi_xs", "sand", "xs", cut="baby")
    r = resolve_sku(_item("GEL-W-HOODIE-XS-SAND"), [kids, baby])
    assert r["uid"] is None, r
    womens = _p("apparel_..._gcu_womens_gco_sand_gsi_xs", "sand", "xs", cut="womens")
    r = resolve_sku(_item("GEL-W-HOODIE-XS-SAND"), [kids, baby, womens])
    assert r["uid"] == womens["uid"], r
    # unisex remains acceptable for either gender
    uni = _p("apparel_..._gcu_unisex_gco_navy_gsi_l", "navy", "l", cut="unisex")
    r = resolve_sku(_item("GEL-M-HOODIE-L-NAVY"), [uni])
    assert r["uid"] == uni["uid"], r


def test_brand_tiebreak_prefers_our_actual_blank():
    # REGRESSION (dry-run finding 3): between two otherwise-equal survivors,
    # the one naming our garment's real blank (Classic hoodie = Lane Seven
    # LS14001) must win - never the cropped TriDri stranger.
    stranger = _p("apparel_..._gcu_womens_gco_white_gsi_xs_tridri_td077",
                  "white", "xs", extra="cropped tridri td077", cut="womens")
    ours = _p("apparel_..._gcu_womens_gco_white_gsi_xs_lane-seven_ls14001",
              "white", "xs", extra="lane seven ls14001", cut="womens")
    r = resolve_sku(_item("GEL-W-HOODIE-XS-WHITE"), [stranger, ours])
    assert r["uid"] == ours["uid"], r


def test_mens_gender_code_is_not_a_size_requirement():
    # REGRESSION (pre-existing, surfaced by the first live dry-run): GEL-M-*
    # tokenises the men's code to 'm', which the dimension gate treated as a
    # REQUIRED SIZE - so a men's L/XL/2XL... SKU could never resolve (only 67
    # of 5,526 candidates survived). The apparel size is parsed structurally:
    # a size-L men's SKU matches a size-l product with no bare 'm' token.
    for size, gsi in (("L", "l"), ("XL", "xl"), ("2XL", "2xl"), ("5XL", "5xl")):
        prod = _p(f"apparel_..._gcu_mens_gco_navy_gsi_{gsi}", "navy", gsi)
        r = resolve_sku(_item(f"GEL-M-HOODIE-{size}-NAVY"), [prod])
        assert r["uid"] == prod["uid"], (size, r)
    # and the size gate still bites: a size-M product never fills a size-L SKU
    wrong = _p("apparel_..._gcu_mens_gco_navy_gsi_m", "navy", "m")
    r = resolve_sku(_item("GEL-M-HOODIE-L-NAVY"), [wrong])
    assert r["uid"] is None, r


def test_aliased_colour_is_hard_too():
    # The alias substitution and the colour dimension compose: DUSTY-ROSE
    # requires dusty AND pink - a plain 'pink' product is not enough.
    plain = _p("apparel_..._gco_pink_gsi_m", "pink", "m")
    r = resolve_sku(_item("GEL-M-HOODIE-M-DUSTY-ROSE"), [plain])
    assert r["uid"] is None, r
    exact = _p("apparel_..._gco_dusty-pink_gsi_m", "dusty-pink", "m")
    r = resolve_sku(_item("GEL-M-HOODIE-M-DUSTY-ROSE"), [plain, exact])
    assert r["uid"] == exact["uid"], r
