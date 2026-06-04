"""Tests for high-ticket gallery-set bundles."""
from quoteforge.etsy.gallery_sets import (
    GALLERY_SETS, GallerySet, set_economics, sets_for_occasion, aov_uplift,
    format_sets_text,
)
from quoteforge import admin


def test_sets_are_high_ticket():
    # The whole point: every set is in the $180-500 high-ticket band.
    for s in GALLERY_SETS:
        assert 180 <= s.set_price <= 500, f"{s.name} priced ${s.set_price}"


def test_every_set_is_multi_piece():
    for s in GALLERY_SETS:
        assert s.pieces >= 3


def test_gelato_cost_scales_with_pieces():
    s = GallerySet("X", "Graduation", "Daughter", 3, "Framed 11x14", 28.0, 219.0)
    assert s.gelato_cost == 84.0


def test_all_sets_meet_50pct_margin_floor():
    # Our own bundles must not violate the margin guard we ship.
    for s in GALLERY_SETS:
        assert s.margin_pct >= 50, f"{s.name} margin {s.margin_pct}%"


def test_set_economics_shape():
    e = set_economics(GALLERY_SETS[0])
    assert e["net_profit"] > 0
    assert e["single_piece_price"] == round(
        GALLERY_SETS[0].set_price / GALLERY_SETS[0].pieces, 2)


def test_sets_for_occasion_matches():
    assert any("Wedding" in s.name or s.occasion == "Wedding"
               for s in sets_for_occasion("wedding"))
    assert sets_for_occasion("") == []


def test_aov_uplift_is_several_x():
    up = aov_uplift(single_price=29.99)
    assert up["aov_multiple"] >= 3.0  # sets lift AOV well above a single poster


def test_format_sets_text():
    text = format_sets_text()
    assert "GALLERY SETS" in text
    assert "Daughter Gallery Trio" in text
    assert "Margin" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_bundles(capsys):
    rc = admin.main(["bundles"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GALLERY SETS" in out


def test_cli_bundles_by_occasion(capsys):
    rc = admin.main(["bundles", "wedding"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Wedding" in out
