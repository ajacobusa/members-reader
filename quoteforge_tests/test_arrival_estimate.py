"""Personalized 'arrives by <date>' estimate in the editor - the top gift-buyer
anxiety (will it arrive in time?) answered with a concrete client-computed date built
from the real PRODUCTION_DAYS + SHIPPING_DAYS.
"""
from PIL import Image


def _page(tmp_path):
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path, out_path=tmp_path / "h.html")
    return out.read_text(encoding="utf-8")


def test_editor_shows_arrival_estimate(tmp_path):
    html = _page(tmp_path)
    assert 'id="marrive"' in html                       # the arrival element exists
    assert "const SHIP_DAYS_TOTAL = 9" in html          # PRODUCTION_DAYS 3 + SHIPPING_DAYS 6
    assert "function _setArrival" in html                # client-side date computation
    assert "function _arriveBy" in html
    assert "arrives by" in html
    assert "_setArrival();" in html                      # called when the editor opens


def test_arrival_total_tracks_config(tmp_path, monkeypatch):
    # The embedded total is production + shipping from config (not a hardcoded number).
    import quoteforge.etsy.listing_preview as lp
    monkeypatch.setattr("quoteforge.config.PRODUCTION_DAYS", 2, raising=False)
    monkeypatch.setattr("quoteforge.config.SHIPPING_DAYS", 5, raising=False)
    html = _page(tmp_path)
    assert "const SHIP_DAYS_TOTAL = 7" in html           # 2 + 5
