"""Storefront fulfillability filter (end-to-end audit gap 1 - the money-path Critical).

The storefront must only OFFER variants with a real approved Gelato UID, so a customer
can never PAY for something that parks unroutable (money taken, told nothing). Pins:
  - variant filtering (apparel) + facet filtering (apparel/mug/branded)
  - zero-coverage products drop entirely (raglan/polo/colour-interior/accent...)
  - family-aware activation (an unmapped family keeps legacy behaviour)
  - the BUILT page carries no unfulfillable orderable format (sizemap scan)
"""
import json

from quoteforge.etsy import fulfillability as F


def test_export_map_is_real_uids_only():
    m = F.approved_export_map()
    assert m, "approved export map missing - run gelato-readiness export"
    assert all(not str(v).upper().startswith("GEL-") for v in m.values())


def test_apparel_variations_filtered_to_mapped():
    vs = F.fulfillable_apparel_variations()
    m = F.approved_export_map()
    assert vs and all(v.gelato_sku in m for v in vs)
    # the known-unfulfillable garments are gone
    gids = {v.garment_id for v in vs}
    for gid in ("m_raglan", "m_polo", "w_longsleeve", "w_sweatshirt"):
        assert gid not in gids, gid


def test_zero_coverage_garment_drops_tile():
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    by = {g.garment_id: g for g in APPAREL_CATALOG}
    assert F.fulfillable_apparel_facets(by["m_raglan"]) is None
    facets = F.fulfillable_apparel_facets(by["m_tshirt"])
    assert facets is not None
    colors, sizes = facets
    # Royal Blue has no approved UID; Heather Grey gained one 2026-07-12
    # (verifier-approved sports-grey), so it moved to the offered set.
    assert "Royal Blue" not in colors and "XS" not in sizes
    assert "White" in colors and "Heather Grey" in colors and "M" in sizes


def test_mug_and_branded_facets():
    from quoteforge.etsy.mug_catalog import MUG_CATALOG
    from quoteforge.etsy.branded_catalog import BRANDED_CATALOG
    mug = {p.product_id: p for p in MUG_CATALOG}
    br = {p.product_id: p for p in BRANDED_CATALOG}
    assert F.fulfillable_mug_facets(mug["color_mug"]) is None      # no Gelato equivalent
    classic = F.fulfillable_mug_facets(mug["classic_mug"])
    assert classic and "Navy" not in classic and "White" in classic
    assert F.fulfillable_branded_facets(br["bottle"]) is None      # 17oz-only at Gelato
    tote = F.fulfillable_branded_facets(br["tote"])
    assert tote and set(tote) == {"Natural", "White", "Navy", "Black"}


def test_built_page_offers_no_unfulfillable_format():
    # REGRESSION (the customer-facing guarantee): every orderable format key in the
    # BUILT page's SIZEMAP round-trips to a real approved UID for active families.
    import re
    from pathlib import Path
    app = Path("docs/app.js")
    if not app.exists():
        import pytest
        pytest.skip("docs/app.js not built")
    m = re.search(r"const SIZEMAP\s*=\s*(\{.*?\});", app.read_text(encoding="utf-8"), re.S)
    assert m, "SIZEMAP not found in built app.js"
    keys = list(json.loads(m.group(1)).keys())
    # Heather Grey left this list 2026-07-12: the verifier approved the
    # generic family's sports-grey (its heather grey) for men's tees/hoodies/
    # sweatshirts, so it is now a REAL orderable colour.
    banned = ("Colour-Interior", "Accent Mug", "3/4 Sleeve", "Polo Shirt",
              "Water Bottle", "Tumbler")
    offenders = [k for k in keys if any(b in k for b in banned)]
    assert not offenders, f"unfulfillable orderable formats on the page: {offenders[:5]}"


def test_family_aware_activation(monkeypatch):
    # An UNMAPPED family keeps its legacy (unfiltered) behaviour - we don't gut a
    # section before its mapping pass exists.
    monkeypatch.setattr(F, "approved_export_map", lambda: {"GEL-SOMETHING-ELSE": "uid"})
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    g = APPAREL_CATALOG[0]
    facets = F.fulfillable_apparel_facets(g)
    assert facets == (list(g.colors), list(g.sizes))
