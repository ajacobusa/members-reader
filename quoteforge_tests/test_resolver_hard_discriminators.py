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


def test_garment_type_is_hard():
    # REGRESSION (top-30 review round 2): GEL-M-TSHIRT-* resolved to gca_hoodie
    # products (the merged catalog pool let a tee claim a hoodie). The product
    # CATEGORY value (gca_/GarmentCategory) must agree with our SKU's type.
    hoodie = {"uid": "apparel_product_gca_hoodie_gcu_mens_gsi_m_gco_white",
              "text": "hoodie white m", "attrs": {"GarmentColor": "white",
              "GarmentSize": "m", "GarmentCategory": "hoodie"}}
    r = resolve_sku(_item("GEL-M-TSHIRT-M-WHITE"), [hoodie])
    assert r["uid"] is None, r
    tee = {"uid": "apparel_product_gca_t-shirt_gcu_mens_gsi_m_gco_white",
           "text": "t-shirt white m", "attrs": {"GarmentColor": "white",
           "GarmentSize": "m", "GarmentCategory": "t-shirt"}}
    r = resolve_sku(_item("GEL-M-TSHIRT-M-WHITE"), [hoodie, tee])
    assert r["uid"] == tee["uid"], r


def test_cross_gender_is_disqualified():
    # REGRESSION (top-30 review round 2): men's SKUs claimed WOMENS cropped
    # hoodies and women's SKUs claimed MENS pullovers. mens<->womens never mix;
    # unisex serves both.
    womens = _p("apparel_gca_hoodie_gcu_womens_gco_white_gsi_m", "white", "m",
                cut="womens")
    r = resolve_sku(_item("GEL-M-HOODIE-M-WHITE"), [womens])
    assert r["uid"] is None, r
    mens = _p("apparel_gca_hoodie_gcu_mens_gco_white_gsi_m", "white", "m",
              cut="mens")
    r = resolve_sku(_item("GEL-W-HOODIE-M-WHITE"), [mens])
    assert r["uid"] is None, r


def test_combo_size_product_never_fills_exact_size_sku():
    # REGRESSION (top-30 review round 2): a size-L SKU matched a gsi_l-xl
    # combo-size product ('l' token subset). The product's size VALUE tokens
    # must all be named by our SKU - l-xl demands both l and xl.
    combo = {"uid": "apparel_gca_hoodie_gcu_mens_gsi_l-xl_gco_white",
             "text": "hoodie white", "attrs": {"GarmentColor": "white",
             "GarmentSize": "l-xl", "GarmentCategory": "hoodie",
             "GarmentCut": "mens"}}
    r = resolve_sku(_item("GEL-M-HOODIE-L-WHITE"), [combo])
    assert r["uid"] is None, r


def test_mug_capacity_matches_gelato_spelling():
    # REGRESSION (top-30 review round 2): every mug scored 0.0 - our '11oz'
    # token never matched Gelato's '11-oz' ({11, oz}). Capacities normalise,
    # and the size-value reverse gate separates 15-oz from 15-oz-travel.
    def mug(size, material):
        return {"uid": f"mug_product_msz_{size}_mmat_{material}_cl_4-0",
                "text": f"mug {size} {material}",
                "attrs": {"MugSize": size, "MugMaterial": material}}
    plain11 = mug("11-oz", "ceramic-white")
    r = resolve_sku({"family": "mug", "sku": "GEL-CLASSIC_MUG-11OZ-WHITE",
                     "tokens": _sku_tokens("mug", "GEL-CLASSIC_MUG-11OZ-WHITE")},
                    [plain11])
    assert r["uid"] == plain11["uid"], r
    # 15-oz-travel must NOT fill the plain LARGE 15oz mug (and vice versa)
    travel15 = mug("15-oz-travel", "stainless-steel-white")
    plain15 = mug("15-oz", "ceramic-white")
    r = resolve_sku({"family": "mug", "sku": "GEL-LARGE_MUG-15OZ-WHITE",
                     "tokens": _sku_tokens("mug", "GEL-LARGE_MUG-15OZ-WHITE")},
                    [travel15, plain15])
    assert r["uid"] == plain15["uid"], r
    r = resolve_sku({"family": "mug", "sku": "GEL-TRAVEL_MUG-15OZ-WHITE",
                     "tokens": _sku_tokens("mug", "GEL-TRAVEL_MUG-15OZ-WHITE")},
                    [travel15, plain15])
    assert r["uid"] == travel15["uid"], r


def test_aliased_colour_is_hard_too():
    # The alias substitution and the colour dimension compose: DUSTY-ROSE
    # requires dusty AND pink - a plain 'pink' product is not enough.
    plain = _p("apparel_..._gco_pink_gsi_m", "pink", "m")
    r = resolve_sku(_item("GEL-M-HOODIE-M-DUSTY-ROSE"), [plain])
    assert r["uid"] is None, r
    exact = _p("apparel_..._gco_dusty-pink_gsi_m", "dusty-pink", "m")
    r = resolve_sku(_item("GEL-M-HOODIE-M-DUSTY-ROSE"), [plain, exact])
    assert r["uid"] == exact["uid"], r
