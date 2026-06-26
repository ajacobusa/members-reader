"""The production build externalizes the heavy main <script> into a cacheable,
deferred app.js (the customer-speed win). Verify the split is correct + lossless,
and that the inline form (the default, used by every other storefront test) is
unaffected.
"""
import re
from pathlib import Path

from PIL import Image


def _build(tmp_path, external):
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    from quoteforge.etsy.listing_preview import build_shop_home
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    return build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                           out_path=tmp_path / "index.html", external_assets=external)


def test_production_build_externalizes_js(tmp_path):
    out = _build(tmp_path, external=True)
    html = out.read_text(encoding="utf-8")
    appjs = tmp_path / "app.js"
    assert appjs.exists(), "app.js was not created"
    js = appjs.read_text(encoding="utf-8")
    # The page references the hashed, deferred bundle (far-future cacheable)...
    assert re.search(r'<script defer src="app\.js\?v=[0-9a-f]{6,}"></script>', html)
    # ...and the engine (DATA + main functions) lives in the bundle, not the page.
    assert "const DATA = " in js
    assert "const DATA = " not in html
    assert "function showFinalProof" in js
    # The gate stays inline so it runs immediately (no deferred dependency).
    assert "sessionStorage.getItem('jf')" in html


def test_inline_build_keeps_js_inline(tmp_path):
    # The default build (used by tests / programmatic callers) is a single
    # self-contained HTML string - no app.js, JS still inline.
    out = _build(tmp_path, external=False)
    html = out.read_text(encoding="utf-8")
    assert not (tmp_path / "app.js").exists()
    assert "const DATA = " in html and "function showFinalProof" in html


def test_externalized_bundle_is_committed_and_referenced():
    # The real committed storefront must ship the bundle the page references.
    docs = Path(__file__).resolve().parents[1] / "docs"
    index = (docs / "index.html").read_text(encoding="utf-8")
    m = re.search(r'src="app\.js\?v=([0-9a-f]{6,})"', index)
    assert m, "docs/index.html does not reference an externalized app.js"
    assert (docs / "app.js").exists(), "docs/app.js missing - run rebuild-site"
