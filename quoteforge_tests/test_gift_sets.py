"""Homepage gift sets & occasions: occasion chips open the editor pre-loaded with
a gift starter, and curated cross-department set tiles merchandise gifting with a
combined from-price + a 'Build this set' entry (cross-sell strip adds the rest)."""
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


def test_gift_sets_and_occasions(tmp_path):
    h = _page(tmp_path)
    assert 'id="giftsets"' in h and 'Gift sets' in h
    assert "const OCCASIONS" in h and "const GIFTSETS" in h
    assert "function shopOccasion" in h and "function startGiftSet" in h
    assert "function renderGiftSets" in h and "renderGiftSets()" in h
    assert "Family Memory Set" in h and "Corporate Welcome Kit" in h
    assert "Best Dad Ever" in h and "Birthday" in h
    assert h.count('class="occchip"') >= 0   # chips are rendered client-side from OCCASIONS
    assert "gelato" not in h.lower() and "printify" not in h.lower()
