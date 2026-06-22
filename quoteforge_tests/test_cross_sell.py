"""Cross-department cross-sell: at the final-design step, offer the same design
on products from OTHER departments ("Make it a gift set") - the AOV lever."""
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
                           out_path=tmp_path / "h.html", frame_picker=True).read_text(encoding="utf-8")


def test_cross_department_cross_sell(tmp_path):
    # REGRESSION: the final-proof modal offers the same design on other departments'
    # products, carrying the customer's wording across the hop (cross-sell / AOV).
    h = _page(tmp_path)
    assert 'id="proofCross"' in h                       # the strip container
    assert "function _crossSellHTML" in h               # builds the suggestions
    assert "function crossSellTo" in h                  # opens the other dept's editor
    assert "function _applyCarry" in h                  # carries the wording across
    assert "Make it a gift set" in h                    # the prompt
    # suggests representative products from the other departments
    assert "Classic Ceramic Mug" in h                   # mug
    assert "Organic Cotton Tote Bag" in h               # branded
    assert "Wall Calendar" in h                         # calendar
    assert "crossSellTo(" in h                          # wired on the buttons
    # no supplier/marketplace leak
    assert "gelato" not in h.lower() and "printify" not in h.lower()
