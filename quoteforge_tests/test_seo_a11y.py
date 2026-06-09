"""Expert-review fixes: SEO meta, accessibility, mobile breakpoints."""
from PIL import Image


def _page(tmp_path):
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    return out.read_text(encoding="utf-8")


def test_seo_meta_present(tmp_path):
    h = _page(tmp_path)
    assert 'name="description"' in h
    assert 'property="og:title"' in h and 'property="og:description"' in h
    assert 'name="twitter:card"' in h
    assert 'rel="canonical"' in h and 'rel="icon"' in h


def test_accessibility(tmp_path):
    h = _page(tmp_path)
    assert 'alt=""' not in h.replace('alt="">', "")  # no empty product alts
    assert 'aria-label="Close"' in h
    assert 'aria-label="Password"' in h and 'aria-label="Your name"' in h
    assert "focus-visible" in h
    assert 'role="button" tabindex="0" aria-label="Personalize' in h  # cards keyboard


def test_mobile_breakpoints(tmp_path):
    h = _page(tmp_path)
    assert "@media(max-width:760px)" in h
    assert ".mleft,.mright{min-width:0" in h
