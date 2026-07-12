"""Colour-alias map + 4XL/5XL size expansion (owner-approved, both grounded in
the LIVE Gelato Product API survey of 2026-07-10):

1. Gelato spells some of our catalogue colours differently (Sage -> dusty-sage,
   Dusty Rose -> dusty-pink, Heather Grey -> grey-heather), so the UID resolver
   could never match those variants and we silently sold fewer colours than the
   print partner can make. GELATO_COLOR_ALIASES feeds the resolver's token set -
   customer-facing names never change.
2. Gelato prints 4XL/5XL for every family we sell except tanks; the catalogue
   now offers them (margin-priced via the existing SIZE_UPCHARGE), and the
   fulfillability layer keeps them invisible until real UIDs are approved.
"""


# ── colour aliases ──────────────────────────────────────────────────────────

def test_alias_map_exists_and_keys_are_catalogue_colours():
    # REGRESSION: aliases must map OUR real catalogue colour names to Gelato
    # colour-uid slugs - a typo'd key would silently alias nothing.
    from quoteforge.etsy.apparel_catalog import GELATO_COLOR_ALIASES, _STD_COLORS
    assert GELATO_COLOR_ALIASES["Sage"] == "dusty-sage"
    assert GELATO_COLOR_ALIASES["Dusty Rose"] == "dusty-pink"
    assert GELATO_COLOR_ALIASES["Heather Grey"] == "grey-heather"
    for k, v in GELATO_COLOR_ALIASES.items():
        assert k in _STD_COLORS, f"alias key {k!r} is not a catalogue colour"
        assert v == v.lower() and " " not in v, f"alias value {v!r} not a slug"


def test_resolver_tokens_substitute_aliased_colours():
    # REGRESSION: GEL-M-HOODIE-M-DUSTY-ROSE previously required the token 'rose'
    # which no Gelato hoodie exposes (their uid is dusty-pink) - unmappable. The
    # alias substitutes the Gelato-side tokens; unaliased colours are untouched.
    from quoteforge.automation.gelato_uid_resolver import _sku_tokens
    t = _sku_tokens("apparel", "GEL-M-HOODIE-M-DUSTY-ROSE")
    assert "pink" in t and "dusty" in t
    assert "rose" not in t
    t = _sku_tokens("apparel", "GEL-M-HOODIE-M-SAGE")
    assert "sage" in t and "dusty" in t          # dusty-sage tokens present
    t = _sku_tokens("apparel", "GEL-M-HOODIE-M-NAVY")
    assert "navy" in t and "pink" not in t       # unaliased colour untouched


def test_resolver_matches_aliased_colour_product():
    # REGRESSION (end to end at the resolver seam): a real-shaped Gelato product
    # whose uid encodes gco_dusty-pink must now RESOLVE for our Dusty Rose SKU,
    # and must NOT resolve for an unrelated colour.
    from quoteforge.automation.gelato_uid_resolver import _sku_tokens, resolve_sku
    product = {"uid": "apparel_product_gca_hoodie_gsc_pullover_gcu_mens_gqa_classic"
                      "_gsi_m_gco_dusty-pink_gpr_0-4",
               "text": "Classic Unisex Pullover Hoodie dusty pink",
               "attrs": {"GarmentColor": "dusty-pink", "GarmentSize": "m",
                         "GarmentCategory": "hoodie"}}
    item = {"family": "apparel", "sku": "GEL-M-HOODIE-M-DUSTY-ROSE",
            "tokens": _sku_tokens("apparel", "GEL-M-HOODIE-M-DUSTY-ROSE")}
    r = resolve_sku(item, [product])
    assert r["uid"] == product["uid"], r
    assert r["confidence"] >= 0.5, r
    other = {"family": "apparel", "sku": "GEL-M-HOODIE-M-NAVY",
             "tokens": _sku_tokens("apparel", "GEL-M-HOODIE-M-NAVY")}
    r2 = resolve_sku(other, [product])
    assert r2["confidence"] < r["confidence"]    # navy sku prefers navy, not pink


# ── 4XL / 5XL expansion ─────────────────────────────────────────────────────

def test_extended_sizes_on_supported_families_only():
    # REGRESSION: Gelato prints 4XL/5XL for tees/longsleeves/raglans/polos/
    # hoodies/sweatshirts but NOT tanks (live catalog survey). Tanks must not
    # offer a size the print partner cannot make.
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    for g in APPAREL_CATALOG:
        if g.garment_type == "tank":
            assert "4XL" not in g.sizes and "5XL" not in g.sizes, g.garment_id
        else:
            assert "4XL" in g.sizes and "5XL" in g.sizes, g.garment_id
        assert g.sizes.index("3XL") < g.sizes.index("4XL") < g.sizes.index("5XL") \
            if "4XL" in g.sizes else True        # order preserved


def test_extended_sizes_are_margin_priced():
    # REGRESSION: 4XL/5XL carry the modeled fulfilment upcharge (+6/+8 on base
    # cost) and the sell price stays above the margin floor - never sold at a
    # 3XL price.
    from quoteforge.etsy.apparel_catalog import build_apparel_variations
    vs = {(v.garment_id, v.size, v.color): v for v in build_apparel_variations()}
    v3 = vs[("m_hoodie", "3XL", "White")]
    v4 = vs[("m_hoodie", "4XL", "White")]
    v5 = vs[("m_hoodie", "5XL", "White")]
    assert v4.gelato_cost > v3.gelato_cost and v5.gelato_cost > v4.gelato_cost
    assert v4.price > v3.price and v5.price > v4.price
    assert v4.margin_pct >= v3.margin_pct - 1    # margin held, not eroded


def test_new_sizes_follow_uid_approval_exactly():
    # REGRESSION: the storefront offers 4XL/5XL EXACTLY where an approved UID
    # backs them (never sell what can't be made, never hide what can). As of
    # 2026-07-12 the verifier-approved set covers m_hoodie 4XL/5XL; m_tshirt's
    # 4XL/5XL are HELD (heavy-weight tier substitution awaiting the owner), so
    # they must stay hidden.
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    from quoteforge.etsy.fulfillability import fulfillable_apparel_facets
    by = {g.garment_id: g for g in APPAREL_CATALOG}
    hoodie = fulfillable_apparel_facets(by["m_hoodie"])
    assert hoodie is not None
    assert "4XL" in hoodie[1] and "5XL" in hoodie[1]
    tee = fulfillable_apparel_facets(by["m_tshirt"])
    assert tee is not None
    assert "4XL" not in tee[1] and "5XL" not in tee[1]


def test_resolver_dimension_tokens_cover_new_sizes():
    # REGRESSION: a 4XL/5XL SKU must only match a Gelato product that positively
    # names that size (the dimension guard knows the new sizes).
    from quoteforge.automation.gelato_uid_resolver import _DIMENSION_TOKENS
    assert "4xl" in _DIMENSION_TOKENS and "5xl" in _DIMENSION_TOKENS


def test_size_menu_sorts_xs_first(tmp_path):
    # REGRESSION (found during the 4XL/5XL work, live on the deployed page): the
    # sizemap sort list lacked XS, so the tank's size menu rendered XS AFTER 3XL
    # (['S','M','L','XL','2XL','3XL','XS']). The full XS..5XL run must sort in
    # wearing order.
    import json
    import re
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    h = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                        out_path=tmp_path / "h.html",
                        frame_picker=True).read_text(encoding="utf-8")
    sm = json.loads(re.search(r"const SIZEMAP = (\{.*?\});", h).group(1))
    order = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
    for key, rows in sm.items():
        sizes = [r["size"] for r in rows]
        known = [s for s in sizes if s in order]
        assert known == sorted(known, key=order.index), f"{key}: {sizes}"


def test_infra_check_guards_alias_map():
    # REGRESSION: the daily sweep verifies the alias map stays sane (keys are
    # real catalogue colours, values are slugs, substitution actually works).
    from quoteforge.automation.infra_check import check_infrastructure
    checks = {c["name"]: c for c in check_infrastructure()["checks"]}
    assert "gelato_color_alias_integrity" in checks
    assert checks["gelato_color_alias_integrity"]["ok"], \
        checks["gelato_color_alias_integrity"]
