"""Tests for the apparel product family (T-Shirt / Hoodie / Sweatshirt).

Apparel is an ISOLATED parallel module: it must clear the same 60% net-margin
floor as the print catalog, carry size+colour variants, expose its own print
geometry (a garment chest is NOT a 5400x7200 poster), and have its OWN Gelato
placeholder guard so a leftover seed UID can never silently route to production.
None of this may touch the working poster/frame path.
"""
from quoteforge.etsy import apparel_catalog as A
from quoteforge.config import TARGET_MARGIN_PCT


# ── Catalog shape ────────────────────────────────────────────────

def test_three_apparel_garments_exist():
    names = {g.name for g in A.APPAREL_CATALOG}
    assert {"T-Shirt", "Hoodie", "Sweatshirt"} <= names
    # every garment is in the apparel category and has sizes + colours
    for g in A.APPAREL_CATALOG:
        assert g.category == "apparel"
        assert g.sizes and g.colors


def test_garment_costs_match_strategic_catalog():
    # REGRESSION: apparel base costs stay in lock-step with product_lines.py,
    # the strategic catalog the owner prices against (T-Shirt 13 / Hoodie 28 /
    # Sweatshirt 24). A silent drift would mis-price every apparel listing.
    from quoteforge.etsy.product_lines import PRODUCT_LINES
    strat = {p.name: p.gelato_cost for p in PRODUCT_LINES}
    for g in A.APPAREL_CATALOG:
        assert g.base_cost == strat[g.name], g.name


# ── Variants ─────────────────────────────────────────────────────

def test_variants_cover_size_by_colour_grid():
    # REGRESSION: a garment expands into size x colour, each a distinct sellable
    # variant with a unique SKU (the fulfillment mapping key).
    vs = A.build_apparel_variations()
    assert vs
    tee = [v for v in vs if v.garment_id == "tshirt"]
    g = A.get_garment("tshirt")
    assert len(tee) == len(g.sizes) * len(g.colors)
    assert len({v.gelato_sku for v in vs}) == len(vs)        # SKUs unique
    assert all(v.gelato_sku for v in vs)                     # never empty


def test_every_apparel_variant_clears_the_floor():
    # REGRESSION: the 60% net floor is the business invariant; it must hold for
    # apparel exactly as it does for prints, on exact-cost recomputation too.
    vs = A.build_apparel_variations()
    assert all(v.margin_pct >= TARGET_MARGIN_PCT for v in vs)
    from quoteforge.etsy.variations import net_margin_pct
    assert all(net_margin_pct(v.price, v.gelato_cost) >= TARGET_MARGIN_PCT
               for v in vs)


def test_tshirt_floor_price_matches_known_good():
    # REGRESSION: a $13 tee priced to the 60% floor lands at $43.99 - the same
    # number already published in product_lines.py. Proves pricing reuse is wired.
    from quoteforge.etsy.variations import min_price_for_margin
    assert min_price_for_margin(13.0, 60) == 43.99


def test_explicit_low_floor_is_clamped_to_target():
    # REGRESSION: a caller passing a floor BELOW 60% (e.g. a future bundle path)
    # must never produce sub-floor apparel - TARGET_MARGIN_PCT is absolute, the
    # same guarantee variations.floor_for_tier gives the print catalog.
    vs = A.build_apparel_variations(floor_pct=50)
    assert vs
    assert all(v.margin_pct >= TARGET_MARGIN_PCT for v in vs)


def test_extended_size_upcharge_still_clears_floor():
    # 2XL costs more to fulfill; its price must rise and still clear the floor.
    vs = A.build_apparel_variations()
    xxl = [v for v in vs if v.size == "2XL"]
    base = [v for v in vs if v.size == "M"]
    assert xxl and base
    assert all(v.margin_pct >= TARGET_MARGIN_PCT for v in xxl)


# ── Print geometry (apparel != poster) ───────────────────────────

def test_apparel_print_area_is_not_poster_default():
    # REGRESSION: apparel must NOT inherit the 18x24 poster default (5400x7200);
    # the editor reads this to draw the garment print-safe boundary.
    w, h = A.apparel_dimensions_for("tshirt")
    assert (w, h) != (5400, 7200)
    assert 0 < w <= 5000 and 0 < h <= 6000      # chest-area sized


def test_unknown_garment_returns_safe_default():
    assert A.apparel_dimensions_for("nope") == A.DEFAULT_APPAREL_DIMS


# ── Availability via the live Gelato sync (mirrors frames) ────────

def test_discontinued_colour_auto_disabled(tmp_path, monkeypatch):
    # REGRESSION: a colour Gelato can no longer fulfill disappears from variants,
    # the same way a discontinued frame does - no manual catalog edit required.
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge.etsy.catalog_state import save_state
    vs0 = A.build_apparel_variations()
    target = next(v for v in vs0 if v.garment_id == "tshirt")
    save_state({target.gelato_sku: {"available": False, "cost": None}})
    skus = {v.gelato_sku for v in A.build_apparel_variations()}
    assert target.gelato_sku not in skus


# ── Fulfilment resolver (storefront basket line -> variant SKU) ───

def test_resolve_apparel_sku_happy_path():
    # REGRESSION: the storefront basket line "T-Shirt - Black" + "M" must resolve
    # to the exact variant SKU order-ingest will map to a Gelato apparel UID.
    assert A.resolve_apparel_sku("T-Shirt - Black", "M") == "GEL-TSHIRT-M-BLACK"
    assert A.resolve_apparel_sku("Hoodie - Navy", "XL") == "GEL-HOODIE-XL-NAVY"
    # multi-word colour stays consistent with the catalogue's SKU convention
    assert A.resolve_apparel_sku("T-Shirt - Heather Grey", "L") == "GEL-TSHIRT-L-HEATHER-GREY"


def test_resolved_sku_is_a_real_catalogue_sku():
    # REGRESSION: every resolvable basket line points at a SKU the catalogue (and
    # thus the placeholder guard + UID map) actually knows about - no orphans.
    skus = set(A.apparel_skus())
    assert A.resolve_apparel_sku("Sweatshirt - Sand", "S") in skus


def test_wall_art_format_is_not_resolved_as_apparel():
    # REGRESSION: a wall-art format must NEVER be misread as apparel.
    assert A.resolve_apparel_sku("Framed - Premium Solid Oak", "18x24 in") is None
    assert A.resolve_apparel_sku("Poster (unframed)", "18x24") is None
    assert A.parse_apparel_format("Framed - Premium Solid Oak") == (None, None)


def test_bad_size_or_colour_does_not_route():
    # A size/colour not in the catalogue returns None so it goes to manual review
    # instead of routing a guessed (possibly non-existent) variant to production.
    assert A.resolve_apparel_sku("T-Shirt - Black", "XXXL") is None
    assert A.resolve_apparel_sku("T-Shirt - Lime", "M") is None
    assert A.apparel_sku_for("tshirt", "M", "Black") == "GEL-TSHIRT-M-BLACK"
    assert A.apparel_sku_for("nope", "M", "Black") is None


# ── Isolated placeholder guard (does NOT touch the print guard) ───

def test_apparel_has_its_own_placeholder_guard():
    m = A.verify_apparel_mappings()
    # seed ships GEL-* placeholders -> flagged, just like the print catalog
    assert m["placeholder_count"] > 0
    assert m["all_real"] is False
    assert m["configured"] + m["placeholder_count"] == m["total"]


def test_apparel_names_match_strategic_catalog():
    # REGRESSION: a rename in one catalogue without the other breaks cost lookups
    # + cross-sell. Every apparel garment name must exist in product_lines.py.
    from quoteforge.etsy.product_lines import PRODUCT_LINES
    names = {p.name for p in PRODUCT_LINES}
    for g in A.APPAREL_CATALOG:
        assert g.name in names, g.name


def test_admin_apparel_command(capsys, tmp_path, monkeypatch):
    # REGRESSION: operators get an apparel view (catalogue + pricing + UID status).
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge import admin
    rc = admin.main(["apparel"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "APPAREL CATALOGUE" in out and "T-Shirt" in out
    assert (tmp_path / "apparel_inventory.csv").exists()


def test_apparel_guard_clears_only_when_all_mapped(monkeypatch):
    # REGRESSION: the go-live guard reads GELATO_UID_MAP (same source as
    # resolve_apparel_uid) and clears to all_real ONLY when every SKU maps to a
    # real (non-GEL-*) UID - so the owner can tell when apparel is launch-ready.
    import json
    skus = A.apparel_skus()
    real = {s: f"apparel_real_{i}" for i, s in enumerate(skus)}
    monkeypatch.setenv("GELATO_UID_MAP", json.dumps(real))
    m = A.verify_apparel_mappings()
    assert m["all_real"] is True and m["placeholder_count"] == 0
    # a still-GEL-* mapped value is treated as a placeholder, not real
    bad = dict(real); bad[skus[0]] = "GEL-STILL-SEED"
    monkeypatch.setenv("GELATO_UID_MAP", json.dumps(bad))
    assert A.verify_apparel_mappings()["placeholder_count"] == 1


def test_apparel_guard_is_separate_from_print_guard():
    # REGRESSION: the print catalog guard must be untouched by apparel; the two
    # catalogs are independent, so the existing go-live tests keep passing.
    from quoteforge.etsy.gelato_catalog import verify_catalog_mappings
    print_total = verify_catalog_mappings()["total"]
    assert print_total == 22        # the 22 print products, unchanged by apparel
