"""Audit #8: the basket money math was only ever asserted by JS-source string presence,
so a wrong threshold/base/rounding would still pass. These tests exercise the CANONICAL
Python pricing (real computed dollar amounts) and PIN the storefront JS discount tiers
to the same single source so they can't drift.
"""


def test_tier_discount_thresholds():
    from quoteforge.etsy.variations import tier_discount
    assert tier_discount(1) == 0.0
    assert tier_discount(2) == 0.08
    assert tier_discount(3) == 0.12
    assert tier_discount(4) == 0.15
    assert tier_discount(10) == 0.15        # largest tier holds above the top threshold


def test_line_subtotal_round_then_multiply():
    from quoteforge.etsy.variations import line_subtotal
    assert line_subtotal(25.0, 2, 0.08) == 46.0      # round(25*0.92,2)=23.00 x2
    assert line_subtotal(30.0, 1, 0.12) == 26.40
    assert line_subtotal(19.99, 3, 0.0) == 59.97


def test_basket_subtotal_discount_keys_off_total_qty():
    from quoteforge.etsy.variations import basket_subtotal
    # single unit, no discount
    assert basket_subtotal([{"unit": 25.0, "qty": 1}]) == 25.0
    # 2 of one product -> total qty 2 -> 8% off that line
    assert basket_subtotal([{"unit": 25.0, "qty": 2}]) == 46.0
    # mixed basket, total qty 3 -> 12% off EVERY line (keys off the total, not per line)
    assert basket_subtotal([{"unit": 25.0, "qty": 2},
                            {"unit": 30.0, "qty": 1}]) == 70.40
    # total qty 4 -> 15%
    assert basket_subtotal([{"unit": 20.0, "qty": 4}]) == 68.0


def test_storefront_tiers_pinned_to_python_source(tmp_path):
    # The emitted JS QD array must equal variations.QTY_DISCOUNT (single source), so the
    # browser discount can never silently diverge from the tested Python tiers.
    import json
    from PIL import Image
    from quoteforge.etsy.variations import QTY_DISCOUNT
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    html = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                           out_path=tmp_path / "h.html").read_text(encoding="utf-8")
    expected = json.dumps([[t, d] for t, d in QTY_DISCOUNT])
    assert expected in html
