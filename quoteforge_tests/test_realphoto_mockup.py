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


def test_cylinder_spins_full_for_wrap_rocks_for_real_photo(tmp_path):
    # REGRESSION: the mug prints a ~300-degree WRAP, so the GENERATED mug now spins a
    # full 360 to show front AND back; a registered real photo can't turn, so it keeps
    # the gentle front rock. (A full turn was previously avoided because the design
    # covered only a small front panel and the back was bare.) Drag always gives full
    # manual control.
    h = _page(tmp_path)
    assert "var rot=0,drag=false,lx=0,dirty=true,hadPhoto=false,tick=0;" in h
    assert "rot=0.42*Math.sin(tick*0.022);" in h          # real photo: gentle front rock
    assert "rot+=0.010" in h                              # generated wrap: slow full 360 spin
    assert "if(dirty){ frame(); dirty=false; }" in h


def test_wrap_covers_most_of_the_mug_leaving_the_handle_gap(tmp_path):
    # The design wraps ~300 degrees of the mug (a real wrap print), confined to that
    # arc so the handle gap stays bare and the front is always centred at rest.
    h = _page(tmp_path)
    assert "Math.abs(rel)<=arc/2" in h            # print confined to its wrap arc
    assert "arc:(handle?5.3:5.6)" in h            # ~300-degree wrap (was a 97-degree panel)


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


# ── Marketing tiles must NOT be a compositing base ──────────────

def test_marketing_tiles_not_used_as_mockup_base(tmp_path):
    # REGRESSION: tile-<id>.jpg are MARKETING photos with a SAMPLE design baked in
    # (e.g. a sunrise on the mug). Compositing the buyer's design on top showed the
    # SAMPLE art, not theirs ("I see the picture not the text"). The marketing maps
    # must NOT be wired into the mockup base; non-apparel uses the generated clean
    # body (or an owner-supplied BLANK photo via brand/mockups).
    h = _page(tmp_path)
    assert "const MUG_IMG" not in h and "const BRANDED_IMG" not in h
    assert "MUG_IMG[" not in h and "BRANDED_IMG[" not in h and "CAL_IMG[" not in h
    assert "function _mockBase" in h


def test_override_photo_shows_in_editor_not_just_spin(tmp_path):
    # REGRESSION: a brand/mockups override exposes `src` (no `front`), so the editor
    # branch must read `_bs.src` - otherwise an override photo rendered in the SPIN
    # but the EDITOR stayed on the generated field.
    h = _page(tmp_path)
    assert "const _bsrc=_bs&&(_bs.src||_bs.front);" in h
    assert "if(_bsrc){ const _i=_mockupImg(_bsrc);" in h
    assert "if(_bs && _bs.front){ const _i=_mockupImg(_bs.front)" not in h


def test_nonapparel_falls_back_to_generated_body(tmp_path):
    # With no owner BLANK override, mug/branded/calendar render the generated field
    # (which shows the buyer's design clearly), not a marketing photo.
    h = _page(tmp_path)
    assert "if(!_mock) _drawMugField" in h
    assert "if(!_mock) _drawBrandedField" in h
    assert "if(!_mock) _drawCalField" in h
    # _mockBase resolves a real photo ONLY for apparel (+ the brand/mockups override)
    assert "Only apparel resolves a real photo here." in h


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
    # REGRESSION: apparel has DISTINCT front/back designs, so the spin must flip
    # between them - using the proof's _composedProofURL + setPlacement, which
    # works on the silhouette OR a real photo (NOT gated on per-colour photos).
    # The old path fell to WebGL _build3D, which only mirrored the FRONT design.
    h = _page(tmp_path)
    assert "function _openFlipReview" in h
    # apparel routes to the flip review, not WebGL
    assert "if(typeof IS_APPAREL!=='undefined' && IS_APPAREL){ _openFlipReview(); return; }" in h
    # the flip reads each side's own design from the proof source + setPlacement
    assert "function _composedProofURL" in h
    assert "function _preloadOne" in h                       # per-URL (front+back) cache
    # REGRESSION: the <img> must NOT be natively draggable, or the browser's image
    # drag-ghost swallows the drag-to-flip (user "cannot spin front and back").
    assert "im.draggable=false" in h
    # and an explicit, discoverable flip control (not just hidden tap/drag)
    assert "See the " in h                                   # "See the back/front" flip button


def test_spin_button_label_is_product_accurate(tmp_path):
    # REGRESSION: "front & back" was promised on single-sided products too. The
    # label is now product-aware: apparel = front & back; cylinder = spin; flat
    # single-face = see-it-on-your-product.
    h = _page(tmp_path)
    assert "Spin your product &mdash; front &amp; back" in h   # apparel
    assert "See it on your product" in h                       # flat single-face


def test_branded_products_show_real_shape_in_editor(tmp_path):
    # The editor previews branded products on their ACTUAL product silhouette (flat,
    # 2D) so the buyer sees the real thing - a keychain reads as a keychain, a tote
    # as a tote - not a mystery grey rectangle.
    h = _page(tmp_path)
    assert "function _drawBrandedShape" in h
    assert "_drawBrandedShape(ctx,x,y,w,h" in h           # the field delegates to the shape
    for kind in ("keychain", "tote", "phone", "journal", "notebook", "mouse", "sticker"):
        assert kind in h, kind                            # a branch per product family


def test_apparel_colour_guard_on_real_photo(tmp_path):
    # REGRESSION: the colour-agnostic side photo only stands in when per-colour
    # photos exist - else a black shirt would render as a white studio shot.
    h = _page(tmp_path)
    assert "if(!hasColor) return null;" in h


def test_open_spin_updates_live_on_edit(tmp_path):
    # REGRESSION: the spin showed a frozen snapshot, so editing text/photo/colour
    # while it was open didn't change it ("cannot change the picture or text").
    # drawArt now flags _SPIN_DIRTY on a real edit (guarded so the spin's own
    # snapshotting doesn't false-trigger), and each open spin re-renders.
    h = _page(tmp_path)
    assert "var _SPIN_DIRTY=false, _SNAPPING=false;" in h
    assert "if(!_SNAPPING) _SPIN_DIRTY=true;" in h            # edit -> dirty
    assert "_SNAPPING=true;" in h                             # read-helpers guard it
    assert "var ns=_designSnap(); if(ns) snap=ns;" in h       # cylinder re-snapshots
    assert "if(_SPIN_DIRTY){ _SPIN_DIRTY=false; _render(); }" in h   # flip review re-renders


def test_product_switch_dismisses_open_spin(tmp_path):
    # REGRESSION: opening the spin on a mug, then switching to a tank top, left the
    # stale mug spin running over the apparel editor (the _openCylSpin loop never
    # stopped). setProductType - the chokepoint every shop*() hits - now dismisses
    # any open spin so the preview never shows the previous product.
    h = _page(tmp_path)
    assert "function setProductType(t){ if(typeof close3D==='function') close3D();" in h
