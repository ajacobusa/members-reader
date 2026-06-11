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


def test_jsonld_structured_data(tmp_path):
    """JSON-LD (Organization/WebSite/Product) is present and valid for rich results."""
    import json
    import re
    h = _page(tmp_path)
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
    assert m, "JSON-LD block missing"
    data = json.loads(m.group(1))           # must parse - no trailing commas etc.
    types = {n.get("@type") for n in data["@graph"]}
    assert {"Organization", "WebSite", "Product"} <= types
    offer = next(n["offers"] for n in data["@graph"] if n.get("@type") == "Product")
    assert offer["@type"] == "AggregateOffer" and offer["priceCurrency"] == "USD"


def test_all_images_have_alt(tmp_path):
    """Every <img> on the page carries alt text (logo, hero, cards, thumbnails)."""
    import re
    h = _page(tmp_path)
    imgs = re.findall(r'<img\b[^>]*>', h)
    missing = [t for t in imgs if "alt=" not in t]
    assert not missing, f"{len(missing)} <img> without alt: {missing[:2]}"


def test_fonts_split_for_performance(tmp_path):
    """Core fonts load normally; the editor-only preview fonts load async
    (media=print onload) so they never block first paint - with a noscript fallback."""
    import re
    h = _page(tmp_path)
    links = re.findall(r'<link\b[^>]*fonts\.googleapis\.com[^>]*>', h)
    # the core link (Cormorant) is render-blocking: no media="print"
    core = [l for l in links if "Cormorant" in l]
    assert core and 'media="print"' not in core[0]
    # the editor-font link (Dancing+Script) is async: media="print" onload swap
    editor = [l for l in links if "Dancing+Script" in l and 'media="print"' in l]
    assert editor and "this.media='all'" in editor[0]
    assert "<noscript><link" in h            # JS-off fallback still loads them


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
