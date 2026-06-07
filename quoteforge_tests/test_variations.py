"""Tests for product variations + 60%-floor pricing."""
from quoteforge.etsy import variations as V
from quoteforge import admin


def test_min_price_clears_floor():
    # A $28 framed cost priced at the 60% floor must net >= 60%.
    price = V.min_price_for_margin(28.0, floor_pct=60)
    assert abs(price - (round(price) - 0.01)) < 1e-9   # ends in .99
    assert V.net_margin_pct(price, 28.0) >= 60
    # a materially lower price would dip below the floor
    assert V.net_margin_pct(round(price - 5.00, 2), 28.0) < 60


def test_all_variations_clear_the_configured_floor():
    # The guarantee follows config.TARGET_MARGIN_PCT - it can't silently drift.
    from quoteforge.config import TARGET_MARGIN_PCT
    vs = V.build_variations()
    assert len(vs) > 0
    assert all(v.margin_pct >= TARGET_MARGIN_PCT for v in vs)
    # exact-cost recomputation (not the rounded display %) also clears the floor
    assert all(
        V.net_margin_pct(v.price, v.gelato_cost) >= TARGET_MARGIN_PCT
        for v in vs)


def test_framed_expands_into_six_frames():
    from quoteforge.etsy.frames import FRAMES
    vs = V.build_variations()
    framed = [v for v in vs if v.material == "framed"]
    assert framed
    # every frame in the 6-tier ladder appears, with its tier set
    assert {v.frame_color for v in framed} == {f.name for f in FRAMES}
    assert {v.frame_tier for v in framed} == {"high", "mid", "low"}
    # non-framed materials carry no frame
    assert all(v.frame_color == "" for v in vs if v.material != "framed")


def test_each_variation_maps_to_a_gelato_sku():
    assert all(v.gelato_sku for v in V.build_variations())  # fulfillment mapping


def test_price_range_and_ladder():
    lo, hi = V.price_range()
    assert 0 < lo < hi
    ladder = V.upsell_ladder()
    assert "entry" in ladder and "mid" in ladder and "top" in ladder


def test_options_block_lists_materials_and_open_canvas():
    block = V.options_block()
    for m in ("Poster", "Framed", "Canvas", "Acrylic", "Metal"):
        assert m in block
    assert "open" in block.lower()           # canvas described as open
    assert "Premium Solid Oak" in block and "Slim Black" in block   # frame ladder


def test_cli_variations_writes_inventory(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    import quoteforge.admin as a
    # admin reads OUTPUT_DIR via the command's local import of config
    rc = a.main(["variations"])
    out = capsys.readouterr().out
    assert rc == 0 and "Price range" in out
    assert (tmp_path / "etsy_inventory.csv").exists()


def test_tier_floors_never_below_global_target():
    from quoteforge.config import TARGET_MARGIN_PCT
    for tier in ("entry", "mid", "top"):
        assert V.floor_for_tier(tier) >= TARGET_MARGIN_PCT


def test_raising_a_tier_floor_lifts_only_that_tier(monkeypatch):
    monkeypatch.setattr("quoteforge.config.MARGIN_FLOOR_TOP", 70.0, raising=False)
    vs = V.build_variations()
    top = [v for v in vs if v.tier == "top"]
    entry = [v for v in vs if v.tier == "entry"]
    assert top and all(v.margin_pct >= 70 for v in top)     # top lifted to 70%
    assert all(v.margin_pct >= 60 for v in entry)           # entry still >=60%


def test_bundle_discount_holds_60_floor():
    # An item listed above the floor gets a real discount but never below 60%.
    cost = 11.0
    from quoteforge.etsy.variations import min_price_for_margin
    listp = min_price_for_margin(cost, 68)           # list at 68%
    for row in V.bundle_table(listp, cost, "entry"):
        assert row["margin_pct"] >= 60               # floor always held
        assert row["holds_floor"] is True
    # buying 4 gives a bigger discount than buying 2
    q2 = V.bundle_quote(listp, cost, 2, "entry")
    q4 = V.bundle_quote(listp, cost, 4, "entry")
    assert q4["discount_pct"] >= q2["discount_pct"] >= 0


def test_bundle_never_below_floor_even_on_thin_margin():
    cost = 40.0
    listp = V.floor_price(cost, "top")               # priced exactly at floor
    q = V.bundle_quote(listp, cost, 4, "top")
    assert q["unit"] >= listp - 0.01 and q["margin_pct"] >= 60   # can't discount below floor
