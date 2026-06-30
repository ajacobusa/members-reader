"""Editor delivery line. A hard 'arrives by <date>' was an over-promise we can't
control (production + multi-carrier variance), so the editor now shows a soft,
non-binding production estimate instead - no calendar date. SHIP_DAYS_TOTAL is still
computed from PRODUCTION_DAYS + SHIPPING_DAYS for internal/SEO use.
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


def test_editor_shows_soft_estimate_not_a_hard_date(tmp_path):
    # REGRESSION: no hard 'arrives by <date>' delivery promise; a soft production line.
    html = _page(tmp_path)
    assert 'id="marrive"' in html                       # the delivery line element exists
    assert "function _setArrival" in html
    assert "_setArrival();" in html                      # called when the editor opens
    assert "arrives by" not in html                     # no delivery-date over-promise
    assert "_arriveBy" not in html
    assert "typically ships in a few business days" in html   # the soft estimate


def test_arrival_total_tracks_config(tmp_path, monkeypatch):
    # The embedded total is production + shipping from config (not a hardcoded number).
    import quoteforge.etsy.listing_preview as lp
    monkeypatch.setattr("quoteforge.config.PRODUCTION_DAYS", 2, raising=False)
    monkeypatch.setattr("quoteforge.config.SHIPPING_DAYS", 5, raising=False)
    html = _page(tmp_path)
    assert "const SHIP_DAYS_TOTAL = 7" in html           # 2 + 5
