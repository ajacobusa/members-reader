"""Free-shipping strategy: bake the shipping cost INTO the displayed price and present
'Free shipping'. Gated OFF by default - it must stay off until the Etsy listings are
themselves set to free shipping, else the buyer pays shipping twice."""
import re
from PIL import Image


def _page(tmp_path):
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path, out_path=tmp_path / "h.html")
    return out.read_text(encoding="utf-8")


def _max_price(html):
    return max(float(x) for x in re.findall(r'"price":\s*"?(\d+\.\d+)"?', html))


def test_free_shipping_off_by_default():
    import quoteforge.config as cfg
    assert cfg.FREE_SHIPPING_BAKED is False           # never reprice the live shop unasked


def test_off_shows_shipping_at_checkout(tmp_path):
    h = _page(tmp_path)
    assert "Tax &amp; shipping are calculated at checkout" in h
    assert "free shipping" not in h.lower()


def test_on_shows_free_shipping_and_keeps_tax_at_checkout(tmp_path, monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "FREE_SHIPPING_BAKED", True)
    h = _page(tmp_path)
    assert "free shipping" in h.lower()                       # the promise
    assert "Tax is calculated at checkout" in h               # tax still at checkout
    assert "shipping are calculated at checkout" not in h     # old line gone


def test_on_bakes_shipping_into_a_higher_price(tmp_path, monkeypatch):
    # REGRESSION: landed price = item + high-end shipping, so prices rise when baked.
    off = _max_price(_page(tmp_path))
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "FREE_SHIPPING_BAKED", True)
    on = _max_price(_page(tmp_path))
    assert on > off + 10                                       # at least a real ship cost
