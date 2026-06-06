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


def test_all_variations_clear_60():
    vs = V.build_variations()
    assert len(vs) > 0
    assert all(v.margin_pct >= 60 for v in vs)


def test_framed_expands_into_frame_colors():
    vs = V.build_variations()
    framed = [v for v in vs if v.material == "framed"]
    assert framed
    assert {v.frame_color for v in framed} == set(V.FRAME_COLORS)
    # non-framed materials carry no frame color
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
    assert "Natural Oak" in block            # frame colors


def test_cli_variations_writes_inventory(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    import quoteforge.admin as a
    # admin reads OUTPUT_DIR via the command's local import of config
    rc = a.main(["variations"])
    out = capsys.readouterr().out
    assert rc == 0 and "Price range" in out
    assert (tmp_path / "etsy_inventory.csv").exists()
