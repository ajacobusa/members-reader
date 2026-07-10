"""PDP chrome (#184): print-partner-style product-page anatomy in the modal.

Pins the structural contract of the product-detail chrome every product family
shares: price + delivery cards keep the ids the JS writers target, size pills
are painted from the SAME SIZEMAP rows as the hidden select (which remains the
single value contract addToOrder reads), and the hero badges carry only honest
made-to-order copy (never fabricated social proof).
"""
from pathlib import Path

from PIL import Image


def _page(tmp_path) -> str:
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    return build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                           out_path=tmp_path / "h.html",
                           frame_picker=True).read_text(encoding="utf-8")


def test_pdp_price_and_delivery_cards(tmp_path):
    # REGRESSION (#184): the two info cards exist and keep the LEGACY ids/classes
    # (#mprice / #marrive) so every existing JS writer updates them unchanged.
    h = _page(tmp_path)
    assert '<div class="pdpcards">' in h
    assert 'class="mprice" id="mprice"' in h
    assert 'class="marrive" id="marrive"' in h
    assert "Your price" in h and ">Delivery<" in h


def test_pdp_size_pills_wrap_the_hidden_select(tmp_path):
    # REGRESSION (#184): pills are the visible picker; the select stays in the
    # DOM as the value contract (visually hidden, never display:none removed).
    h = _page(tmp_path)
    assert 'id="msizepills"' in h
    assert "function _paintSizePills" in h and "function pickSizePill" in h
    assert 'class="szselwrap"' in h                    # select kept, sr-hidden
    assert 'id="msize" onchange="onSizeChange()"' in h  # same change path
    # pill click drives the SELECT (single value contract), not a parallel state
    assert "sel.selectedIndex=i; onSizeChange();" in h


def test_pdp_subtitle_and_named_colour_label(tmp_path):
    # REGRESSION (#184): one honest benefit line under the title per family, and
    # the swatch row NAMES the picked colour (close shades are ambiguous as dots).
    h = _page(tmp_path)
    assert 'id="msub"' in h
    assert "Premium garment, printed with your design, made to order" in h
    assert "Personalized wall art, printed and shipped to you" in h
    assert "function _updColorLabel" in h
    assert "_updColorLabel(cn); }}".replace("}}", "}") in h or "_updColorLabel(cn);" in h


def test_pdp_hero_badges_are_honest(tmp_path):
    # REGRESSION (#184): badges carry only true made-to-order claims; no
    # fabricated social proof ("Bestseller"/"Trending") pre-launch.
    h = _page(tmp_path)
    assert ">Made to order</span>" in h
    assert ">You approve before print</span>" in h
    assert "pointer-events:none" in h                  # badges never block drag
    for fake in (">Bestseller<", ">Trending<", ">Popular<"):
        assert fake not in h, f"fabricated social proof: {fake}"
