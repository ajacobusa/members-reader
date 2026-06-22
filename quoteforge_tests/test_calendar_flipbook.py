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


def test_calendar_12month_flipbook(tmp_path):
    h = _page(tmp_path)
    assert 'id="mcalbar"' in h and 'id="flipPop"' in h
    assert "function _drawMonthGrid" in h and "function _drawCalPage" in h
    assert "function openFlipbook" in h and "function renderCalSlots" in h
    assert "let CAL_PHOTOS" in h and "function calPhotoUpload" in h
    assert "Preview calendar" in h and "12-month calendar" in h
    assert "gelato" not in h.lower() and "printify" not in h.lower()
