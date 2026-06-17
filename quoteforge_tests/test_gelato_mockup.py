"""Supplier product-mockup integration: real product images for the storefront.

The invariant that protects production: this is a NO-OP until the owner is truly
live (key set + real UIDs mapped). In TEST_MODE, without a key, or for a leftover
placeholder GEL-* UID it returns None and the storefront keeps the AI tile - so a
half-configured account never ships broken image URLs.
"""
import json

from quoteforge.images import supplier_mockup as gm


def _go_live(monkeypatch, uid_map, fetch):
    """Flip the module into 'live' mode: TEST_MODE off, key set, UID map + fetch."""
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "k_live")
    monkeypatch.setattr("quoteforge.automation.gelato_sync._uid_map", lambda: uid_map)
    monkeypatch.setattr(gm, "_fetch_product_image", fetch)


# ── Guard: no-op until genuinely live ────────────────────────────

def test_test_mode_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    assert gm.gelato_blank_image("GEL-M-TSHIRT-M-WHITE") is None


def test_no_key_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "")
    assert gm.gelato_blank_image("GEL-M-TSHIRT-M-WHITE") is None


def test_placeholder_uid_returns_none(tmp_path, monkeypatch):
    # REGRESSION: a leftover seed GEL-* UID must be treated as unmapped, never
    # fetched - mirrors the go-live placeholder guard.
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    _go_live(monkeypatch, {"GEL-M-TSHIRT-M-WHITE": "GEL-STILL-SEED"},
             lambda uid: "http://x/should-not-be-called.png")
    assert gm.gelato_blank_image("GEL-M-TSHIRT-M-WHITE") is None


def test_unmapped_sku_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    _go_live(monkeypatch, {}, lambda uid: "http://x/y.png")
    assert gm.gelato_blank_image("GEL-NOPE") is None


# ── Live fetch + cache ───────────────────────────────────────────

def test_real_uid_fetches_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    calls = []
    def fetch(uid):
        calls.append(uid)
        return "http://cdn/real-tee.png"
    _go_live(monkeypatch, {"GEL-M-TSHIRT-M-WHITE": "real_uid_123"}, fetch)
    assert gm.gelato_blank_image("GEL-M-TSHIRT-M-WHITE") == "http://cdn/real-tee.png"
    # second call is served from cache - the API isn't hit again
    monkeypatch.setattr(gm, "_fetch_product_image",
                        lambda uid: "http://cdn/DIFFERENT.png")
    assert gm.gelato_blank_image("GEL-M-TSHIRT-M-WHITE") == "http://cdn/real-tee.png"
    assert len(calls) == 1
    cache = json.loads((tmp_path / "gelato_mockups.json").read_text())
    assert cache["GEL-M-TSHIRT-M-WHITE"] == "http://cdn/real-tee.png"


def test_extract_image_url_shapes():
    f = gm._extract_image_url
    assert f({"previewUrl": "http://a/x.png"}) == "http://a/x.png"
    assert f({"images": ["http://b/y.png"]}) == "http://b/y.png"
    assert f({"images": [{"url": "http://c/z.png"}]}) == "http://c/z.png"
    assert f({"mockups": [{"fileUrl": "http://d/w.png"}]}) == "http://d/w.png"
    assert f({"nope": 1}) is None
    assert f("not a dict") is None


def test_apparel_tile_images_empty_in_test_mode():
    # TEST_MODE: no network, returns {} so the storefront keeps the AI tiles.
    assert gm.apparel_tile_images() == {}


# ── Storefront wiring ────────────────────────────────────────────

def test_storefront_uses_supplier_image_when_present(tmp_path, monkeypatch):
    # REGRESSION: when a real supplier image resolves for a garment type, the tile
    # <img src> uses it (overriding the AI tile). Patch at the source module so the
    # in-function import in build_shop_home picks it up.
    monkeypatch.setattr(gm, "apparel_tile_images",
                        lambda *a, **k: {"tshirt": "https://cdn/partner-tee.png"})
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert 'src="https://cdn/partner-tee.png"' in h


def test_admin_gelato_mockups_command(capsys):
    from quoteforge import admin
    rc = admin.main(["gelato-mockups"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AI tiles remain in use" in out      # TEST_MODE: no-op message
