"""Real product-photo mockups + the never-blank 3D cylinder.

The "View in 3D" preview is the key selling picture. Two invariants protect it:

1. A cylindrical product (mug / bottle / tumbler) NEVER shows a blank white
   cylinder: it routes to a realistic 2D body (or, when registered, the buyer's
   design composited onto a REAL product photo) and rests CENTRED so the design
   always faces front.
2. The real-photo path is owner-supplied and auto-upgrading: empty by default
   (so a half-set-up shop never ships a broken image) and customer-safe (it emits
   image bytes + geometry only, never a supplier/marketplace name).
"""
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
                           out_path=tmp_path / "h.html",
                           frame_picker=True).read_text(encoding="utf-8")


# ── The mockup engine is present and wired ───────────────────────

def test_realphoto_engine_functions_present(tmp_path):
    h = _page(tmp_path)
    for fn in ("function _openCylSpin", "function _wrapInto",
               "function _drawCylBody", "function _photoMockupURL",
               "function _showFlatPhoto", "function _mockSpec",
               "function _preloadMock", "function _designSnap",
               "const MOCKUP_PHOTOS"):
        assert fn in h, f"mockup-engine symbol missing: {fn}"


def test_realphoto_manifest_empty_by_default(tmp_path):
    # No photos dropped in -> empty manifest -> the editor uses its generated
    # mockup. A half-configured shop must never ship a broken image URL.
    import json
    import re
    h = _page(tmp_path)
    m = re.search(r"const MOCKUP_PHOTOS = (\{.*?\});", h)
    assert m, "MOCKUP_PHOTOS manifest not emitted"
    assert json.loads(m.group(1)) == {}


# ── REGRESSION: the blank-white-cylinder bug ─────────────────────

def test_cylinder_routes_to_realistic_spin(tmp_path):
    # REGRESSION: a mug/bottle/tumbler used to wrap the near-empty flat proof
    # around a 360deg WebGL cylinder, so the front read as a BLANK white barrel.
    # view3D now routes every cylindrical product to the 2D realistic body, which
    # always carries the design on its front. Verified live in-browser too.
    h = _page(tmp_path)
    assert "if((typeof _isCyl==='function')&&_isCyl()){ _openCylSpin(); return; }" in h
    # the generated body is a real shape (rounded body + accent), not a flat fill
    assert "createLinearGradient" in h and "quadraticCurveTo" in h


def test_cylinder_rests_centered_not_auto_spun(tmp_path):
    # REGRESSION: the preview rests CENTRED (design facing front = a clear
    # picture); the buyer drags to spin. It must NOT auto-rotate the design off
    # the front on open (which re-created a "blank" front mid-spin).
    h = _page(tmp_path)
    assert "var rot=0,drag=false,lx=0,dirty=true,hadPhoto=false;" in h
    assert "rot+=0.006" not in h            # no idle auto-rotate
    # the loop re-renders only when dirty (drag / late photo load), never auto-spins
    assert "if(dirty){ frame(); dirty=false; }" in h


def test_wrap_leaves_back_bare_never_blank_front(tmp_path):
    # The wrap paints the print only across its barrel arc and leaves the rest of
    # the body/photo bare, so a spin reveals a clean back AND the design always
    # sits on the front at rest (rot 0 -> centred print).
    h = _page(tmp_path)
    assert "Math.abs(rel)<=arc/2" in h      # print confined to its front arc


# ── The WebGL flat-panel path is still intact (unchanged products) ─

def test_flat_panel_webgl_path_intact(tmp_path):
    # Posters / canvas / apparel / tote still use the (recently fixed) WebGL flat
    # panel - the new engine only takes over the cylindrical + real-photo cases.
    h = _page(tmp_path)
    for marker in ("function _build3D", "CylinderGeometry", "BoxGeometry(pw,ph",
                   "map:texB", "texB.repeat.x=-1"):
        assert marker in h, f"flat-panel 3D marker lost: {marker}"


# ── Customer-safe: no supplier/marketplace names anywhere on the page ─

def test_mockup_pipeline_no_supplier_leak(tmp_path):
    h = _page(tmp_path).lower()
    for banned in ("gelato", "printify", "printful"):
        assert banned not in h, f"supplier name leaked to customer page: {banned}"


# ── Python: owner-supplied photo is discovered, keyed by product NAME ─

def test_dropped_photo_is_discovered_and_composited(tmp_path, monkeypatch):
    # Drop a real product photo + geometry sidecar under brand/mockups/ and the
    # build registers it under the product NAME the editor carries, so the live
    # design composites onto it. (REGRESSION: keyed by name, not product_id.)
    import json
    monkeypatch.chdir(tmp_path)
    mock = tmp_path / "brand" / "mockups"
    mock.mkdir(parents=True)
    Image.new("RGB", (640, 640), (210, 214, 218)).save(mock / "classic_mug.png")
    (mock / "classic_mug.json").write_text(
        json.dumps({"area": [0.3, 0.35, 0.4, 0.34], "cyl": True, "span": 1.8}),
        encoding="utf-8")
    h = _page(tmp_path)
    import re
    m = re.search(r"const MOCKUP_PHOTOS = (\{.*?\});", h)
    assert m, "MOCKUP_PHOTOS not emitted"
    data = json.loads(m.group(1))
    assert "Classic Ceramic Mug (11oz)" in data, \
        "dropped photo not keyed by product name"
    spec = data["Classic Ceramic Mug (11oz)"]
    assert spec["cyl"] is True and spec["span"] == 1.8
    assert spec["area"] == [0.3, 0.35, 0.4, 0.34]
    assert spec["src"]                      # an emitted image source, not empty
    # even with a real photo registered, no supplier name leaks
    assert "gelato" not in h.lower()


def test_missing_mockups_dir_is_harmless(tmp_path, monkeypatch):
    # No brand/mockups dir -> empty manifest, build still succeeds.
    monkeypatch.chdir(tmp_path)
    h = _page(tmp_path)
    assert "const MOCKUP_PHOTOS = {};" in h


# ── Real photos from the EXISTING pipeline feed the editor + spin ─

def test_tile_photos_exposed_to_editor_js(tmp_path):
    # The real tile-<id>.jpg photos (downloaded by the product-photos agent, used
    # by the grid tiles) are now also exposed to the editor preview + spin.
    h = _page(tmp_path)
    for m in ("const MUG_IMG", "const BRANDED_IMG", "const CAL_IMG",
              "function _mockBase"):
        assert m in h, f"missing real-photo wiring: {m}"


def test_editor_renders_on_real_photo_for_nonapparel(tmp_path):
    # REGRESSION: mug / branded / calendar render the design on the REAL product
    # photo when present (generated field only as fallback) - matching apparel.
    h = _page(tmp_path)
    assert "else if(IS_MUG||IS_BRANDED||IS_CAL){" in h    # real-photo resolution
    assert "if(!_mock) _drawMugField" in h
    assert "if(!_mock) _drawBrandedField" in h
    assert "if(!_mock) _drawCalField" in h


def test_tile_photo_auto_feeds_mockup_map(tmp_path, monkeypatch):
    # Drop a real tile photo and it flows into the editor JS map (no separate
    # manual folder needed) - the pipeline the product-photos agent already feeds.
    import json
    import re
    monkeypatch.chdir(tmp_path)
    (tmp_path / "brand").mkdir()
    Image.new("RGB", (400, 400), (40, 120, 120)).save(
        tmp_path / "brand" / "tile-classic_mug.jpg")
    h = _page(tmp_path)
    m = re.search(r"const MUG_IMG = (\{.*?\});", h)
    assert m and "classic_mug" in json.loads(m.group(1))


# ── REGRESSION: spin is inline on the product, not a separate 3D popup ─

def test_spin_is_inline_on_product(tmp_path):
    # REGRESSION: the spin overlays the product preview in place (so the customer
    # rotates the REAL product they designed) - the old full-screen 3D modal popup
    # and the "View in 3D" label are gone.
    h = _page(tmp_path)
    assert 'id="mug3dwrap" style="display:none;position:absolute;inset:0' in h
    assert "position:fixed;inset:0;z-index:9999" not in h     # old popup removed
    assert "Spin your product" in h
    assert "View in 3D" not in h


# ── Rotate to review front AND back ──────────────────────────────

def test_front_back_flip_wired(tmp_path):
    # The buyer can rotate to review their customization on BOTH sides: cylinders
    # spin the wrap; apparel flips between the real front and back photos (each
    # side's own design). Photos preload per-URL so both sides resolve.
    h = _page(tmp_path)
    assert "function _preloadOne" in h                       # per-URL (front+back) cache
    assert "side==='back')?back:url" in h                    # src follows APPLACEMENT
    assert "tap to flip" in h                                # apparel front/back affordance
    assert "if(base && base.back && typeof setPlacement==='function'){" in h


def test_apparel_colour_guard_on_real_photo(tmp_path):
    # REGRESSION: the colour-agnostic side photo only stands in when per-colour
    # photos exist - else a black shirt would render as a white studio shot.
    h = _page(tmp_path)
    assert "if(!hasColor) return null;" in h
