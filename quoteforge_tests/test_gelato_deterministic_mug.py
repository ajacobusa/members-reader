"""Deterministic mug UID mapping — attribute match against the REAL Gelato UID grammar.

Fuzzy token-matching scores ~0 against Gelato's coded productUids, so we map by parsed
attributes (size + MATERIAL + colour). These pin the correctness that matters:
  - material-anchored, so ceramic-black is NOT mis-mapped to heat-transfer-black
  - a product Gelato doesn't make (colour-interior, accent) is flagged UNFULFILLABLE,
    never silently mapped to a full-colour ceramic mug
  - a colour Gelato doesn't offer (navy) is flagged, never guessed into 'blue'
Hermetic: an injected catalog, no network.
"""
from quoteforge.automation import gelato_uid_resolver as rs


# A tiny slice of the REAL Gelato mug catalog (grammar verified live), incl. the
# ceramic-black / heat-transfer-black collision at 11-oz.
_CATALOG = [{"uid": u} for u in (
    "mug_product_msz_11-oz_mmat_ceramic-white_cl_4-0",
    "mug_product_msz_11-oz_mmat_ceramic-black_cl_4-0",
    "mug_product_msz_11-oz_mmat_ceramic-red_cl_4-0",
    "mug_product_msz_11-oz_mmat_ceramic-green_cl_4-0",
    "mug_product_msz_11-oz_mmat_heat-transfer-black_cl_4-0",   # collision decoy
    "mug_product_msz_15-oz_mmat_ceramic-white_cl_4-0",
    "mug_product_msz_17-oz-tall_mmat_ceramic-white_cl_4-0",
    "mug_product_msz_12-oz-enamel_mmat_metal-enamel-white_cl_4-0",
    "mug_product_msz_15-oz-travel_mmat_stainless-steel-white_cl_4-0",
)]


def _by_sku():
    return {r["sku"]: r for r in rs.deterministic_mug_matches(catalog=_CATALOG)}


def test_parse_extracts_size_material_colour():
    p = rs._parse_gelato_mug_uid("mug_product_msz_11-oz_mmat_heat-transfer-black_cl_4-0")
    assert p == {"size": "11-oz", "material": "heat-transfer", "colour": "black",
                 "uid": "mug_product_msz_11-oz_mmat_heat-transfer-black_cl_4-0"}


def test_classic_black_maps_to_ceramic_not_heat_transfer():
    # REGRESSION: the same-colour collision must resolve to the ceramic product (our
    # material), never the heat-transfer variant.
    r = _by_sku().get("GEL-CLASSIC_MUG-11OZ-BLACK")
    assert r and r["status"] == "matched"
    assert r["uid"] == "mug_product_msz_11-oz_mmat_ceramic-black_cl_4-0"


def test_classic_matches_available_colours():
    m = _by_sku()
    assert m["GEL-CLASSIC_MUG-11OZ-WHITE"]["status"] == "matched"
    assert m["GEL-CLASSIC_MUG-11OZ-RED"]["status"] == "matched"


def test_navy_is_unfulfillable_not_guessed_as_blue():
    # REGRESSION: Gelato has no navy; it must be flagged, never coerced to 'blue'.
    r = _by_sku().get("GEL-CLASSIC_MUG-11OZ-NAVY")
    assert r and r["status"] == "unfulfillable" and r["uid"] is None
    assert "navy" in r["reason"].lower()


def test_colour_interior_has_no_gelato_equivalent():
    # REGRESSION: colour-interior is NOT a full-colour ceramic mug; every variant must be
    # flagged unfulfillable, never mapped to ceramic-{colour}.
    rows = [r for r in rs.deterministic_mug_matches(catalog=_CATALOG)
            if r["product_id"] == "color_mug"]
    assert rows and all(r["status"] == "unfulfillable" and r["uid"] is None for r in rows)


def test_accent_has_no_gelato_equivalent():
    rows = [r for r in rs.deterministic_mug_matches(catalog=_CATALOG)
            if r["product_id"] == "accent_mug"]
    assert rows and all(r["status"] == "unfulfillable" for r in rows)


def test_15oz_black_unfulfillable_white_only():
    m = _by_sku()
    assert m["GEL-LARGE_MUG-15OZ-WHITE"]["status"] == "matched"
    assert m["GEL-LARGE_MUG-15OZ-BLACK"]["status"] == "unfulfillable"


def test_specialty_mugs_match_their_material():
    m = _by_sku()
    assert m["GEL-ENAMEL_MUG-12OZ-WHITE"]["uid"].endswith("metal-enamel-white_cl_4-0")
    assert m["GEL-TRAVEL_MUG-15OZ-WHITE"]["uid"].endswith("stainless-steel-white_cl_4-0")
    assert m["GEL-XL_MUG-17OZ-WHITE"]["uid"].startswith("mug_product_msz_17-oz-tall")


def test_no_placeholder_or_wrong_family_uid_ever_returned():
    # Every matched uid is a real, parseable mug uid (never a GEL-* placeholder).
    for r in rs.deterministic_mug_matches(catalog=_CATALOG):
        if r["status"] == "matched":
            assert not r["uid"].upper().startswith("GEL-")
            assert rs._parse_gelato_mug_uid(r["uid"]) is not None


# ── bottle + tote deterministic mapping (same rigor: verified vs live grammar) ──

def test_bottle_size_gap_flagged_unfulfillable():
    # Gelato bottles catalog is 17oz-only; our 20oz must flag, never mis-map to 17oz.
    cat = [{"uid": "bottle_product_bsz_17-oz_bmat_stainless-steel-white_cl_4-0"}]
    rows = rs.deterministic_bottle_matches(catalog=cat)
    assert rows and all(r["status"] == "unfulfillable" for r in rows if "20OZ" in r["sku"])


def test_tote_matches_clean_colour_variant_only():
    cat = [{"uid": u} for u in (
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_black_bpr_4-0",
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_natural_bpr_4-0",
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_navy_bpr_4-0",
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_white_bpr_4-0",
        # decoys that must NOT match (embroidery / manufacturer variants):
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_black_bpr_4-0-emb_westford-mill_w101",
    )]
    by = {r["sku"]: r for r in rs.deterministic_bag_matches(catalog=cat)}
    assert by["GEL-TOTE-ONE-SIZE-BLACK"]["uid"] == \
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_black_bpr_4-0"
    assert by["GEL-TOTE-ONE-SIZE-NAVY"]["status"] == "matched"
    # sand/sage have no clean Gelato variant -> unfulfillable, never guessed
    assert by["GEL-TOTE-ONE-SIZE-SAND"]["status"] == "unfulfillable"
    assert by["GEL-TOTE-ONE-SIZE-SAGE"]["status"] == "unfulfillable"


def test_bag_canonical_rejects_non_canonical_variants():
    # only the single-side full-colour, standard-quality, no-manufacturer variant is canonical
    assert rs._bag_canonical_colour(
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_white_bpr_4-0") == "white"
    assert rs._bag_canonical_colour(
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_white_bpr_4-4") is None
    assert rs._bag_canonical_colour(
        "bag_product_bsc_tote-bag_bqa_clc_bsi_std-t_bco_white_bpr_4-0-emb_westford-mill_w101") is None


# ── apparel: construct-and-verify (hermetic via injected verifier) ─────────────

def test_apparel_uid_construction():
    assert rs._apparel_uid("t-shirt", "crewneck", "unisex", "classic", "l", "white") == \
        "apparel_product_gca_t-shirt_gsc_crewneck_gcu_unisex_gqa_classic_gsi_l_gco_white_gpr_0-4"


def test_apparel_matches_only_verified_existing_uids():
    # verifier accepts only t-shirt unisex classic L/white -> exactly that SKU matches.
    def verify(uid):
        return uid == ("apparel_product_gca_t-shirt_gsc_crewneck_gcu_unisex_gqa_classic"
                       "_gsi_l_gco_white_gpr_0-4")
    rows = rs.deterministic_apparel_matches(quality="classic", verifier=verify)
    m = [r for r in rows if r["status"] == "matched"]
    assert m, "expected at least one match"
    assert all(r["uid"].endswith("_gsi_l_gco_white_gpr_0-4") for r in m)
    # a colour Gelato didn't verify (e.g. black) must be unfulfillable, never guessed
    black = [r for r in rows if r["colour"].lower() == "black" and r["garment_id"] == "m_tshirt"]
    assert black and all(r["status"] == "unfulfillable" for r in black)


def test_apparel_unconfirmed_garment_flagged_not_guessed():
    # hoodie/polo/longsleeve/raglan subcategories are unconfirmed -> always unfulfillable
    rows = rs.deterministic_apparel_matches(quality="classic", verifier=lambda u: True)
    for gt in ("hoodie", "polo", "longsleeve", "raglan"):
        gr = [r for r in rows if r["garment_id"] in (f"m_{gt}", f"w_{gt}")]
        assert gr and all(r["status"] == "unfulfillable" for r in gr), gt


def test_apparel_never_returns_placeholder():
    rows = rs.deterministic_apparel_matches(quality="classic", verifier=lambda u: True)
    for r in rows:
        if r["status"] == "matched":
            assert not r["uid"].upper().startswith("GEL-")
            assert rs._parse_gelato_apparel_uid(r["uid"]) is not None
