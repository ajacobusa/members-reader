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


def test_mug_section_renders_products_and_facets(tmp_path):
    h = _page(tmp_path)
    assert 'id="deptMug"' in h
    assert 'class="appcard mugcard"' in h
    assert h.count('data-mpid="') >= 7
    assert 'data-mpid="classic_mug"' in h and 'data-mpid="enamel_mug"' in h
    assert 'mugfilter' in h
    assert 'shopMug(' in h
    assert 'MUG_FORMATS' in h and 'MUG_DIMS' in h
    assert "gelato" not in h.lower() and "printify" not in h.lower()


def test_mug_is_a_department(tmp_path):
    h = _page(tmp_path)
    assert 'href="#mugs"' in h
    assert 'deptmug' in h
    assert 'id="deptMug"' in h
    assert "selectDept('mug')" in h
    assert h.count("selectDept(") >= 4
    assert "function applyMugFilters" in h and "function clearMugFilters" in h


def test_mug_editor_mode_wired(tmp_path):
    h = _page(tmp_path)
    assert "let IS_MUG" in h
    assert "function shopMug" in h
    assert "MUG_FORMATS" in h and "MUG_DIMS" in h
    assert "function _drawMugField" in h
    assert ("IS_APPAREL||IS_BRANDED||IS_MUG" in h) or ("IS_MUG" in h and "_drawMugField" in h)


def test_mug_no_supplier_leak(tmp_path):
    # REGRESSION: mug copy never exposes a print supplier.
    h = _page(tmp_path).lower()
    for bad in ("gelato", "printify", "printful"):
        assert bad not in h, bad


def test_mug_wrap_preview_in_proof(tmp_path):
    # REGRESSION: the mug final proof shows the design WRAPPED on a realistic mug
    # (cylinder warp + handle + accent rim), not the flat design panel.
    h = _page(tmp_path)
    assert "function _drawMugMockup" in h
    assert "function _mugMockupURL" in h
    assert "IS_MUG?_mugMockupURL()" in h


def test_mug_wrap_preserves_design_aspect(tmp_path):
    # REGRESSION: the wrap must keep the design's true aspect (no vertical stretch
    # onto a near-square body) - the auditor's print-fidelity NO-GO fix.
    h = _page(tmp_path)
    assert "aspect-true height" in h
    assert "var drawnH=Math.min(" in h


def test_layout_elements_are_individually_draggable():
    # The badge/emblem layouts let the buyer NUDGE each word + the photo (per-element
    # offsets), with a Reset to restore the template - not a locked template.
    import pathlib
    from quoteforge.etsy import listing_preview as lp
    src = pathlib.Path(lp.__file__).read_text(encoding="utf-8")
    for marker in ("let LOFF=", "function _loff", "function resetPlacement",
                   "DRAGTARGET.indexOf('slot:')", "return 'slot:'+s.slot"):
        assert marker in src, f"per-element drag marker missing: {marker}"


def test_layout_wording_inputs_live_in_the_design_step(tmp_path):
    # REGRESSION: when a layout is active the freeform textarea is hidden; the per-line
    # slot inputs must appear in Step 1 (the Design step), not only in the left layout
    # bar - otherwise the buyer 'cannot add or modify text'.
    h = _page(tmp_path)
    assert 'id="mslotbox"' in h
    i_e1, i_slots, i_e2 = (h.find('id="esec1"'), h.find('id="mslots"'),
                           h.find('id="esec2"'))
    assert i_e1 > 0 and i_e2 > i_e1
    assert i_e1 < i_slots < i_e2          # wording inputs are inside the Design step


def test_mug_and_calendar_show_real_sizes_not_poster_fallback(tmp_path):
    # REGRESSION: the mug/calendar Size dropdown must show real sizes/prices (mug
    # capacity 11oz, calendar A3/A4) - not fall back to poster sizes (8x10..24x36).
    import json
    import re
    h = _page(tmp_path)
    sm = json.loads(re.search(r'const SIZEMAP = (\{.*?\});', h).group(1))
    mug_keys = [k for k in sm if "oz" in k.lower()]
    assert mug_keys, "no mug format keys in SIZEMAP - mug falls back to poster sizes"
    mug_sizes = [r["size"] for r in sm[mug_keys[0]]]
    assert any("oz" in s for s in mug_sizes)          # capacity, not 24x36
    assert not any("x" in s for s in mug_sizes)        # never a poster size
    cal_keys = [k for k in sm if "calendar" in k.lower()]
    assert cal_keys and all("oz" not in s["size"] for s in sm[cal_keys[0]])
