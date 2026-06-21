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


def test_branded_base_colours_have_swatches(tmp_path):
    # REGRESSION: branded base materials (Natural/Cream/Silver) need hex swatches
    # in the shared colour map so the editor renders them.
    h = _page(tmp_path)
    for c in ('"Natural"', '"Cream"', '"Silver"'):
        assert c in h, c


def test_branded_section_renders_products_and_facets(tmp_path):
    h = _page(tmp_path)
    assert 'id="deptBranded"' in h
    assert 'class="brandcard"' in h
    assert h.count('data-bpid="') >= 9
    assert 'data-bpid="tote"' in h and 'data-bpid="bottle"' in h
    assert 'class="brandfilter"' in h
    assert 'shopBranded(' in h
    assert 'BRANDED_FORMATS' in h and 'BRANDED_DIMS' in h
    assert "gelato" not in h.lower() and "printify" not in h.lower()


def test_branded_is_a_third_department(tmp_path):
    h = _page(tmp_path)
    assert 'href="#branded"' in h
    assert 'deptbranded' in h
    assert 'id="deptBranded"' in h
    assert "selectDept('branded')" in h
    assert h.count("selectDept(") >= 3
    assert "function applyBrandedFilters" in h and "function clearBrandedFilters" in h


def test_branded_editor_mode_wired(tmp_path):
    h = _page(tmp_path)
    assert "let IS_BRANDED" in h
    assert "function shopBranded" in h
    assert "BRANDED_FORMATS" in h and "BRANDED_DIMS" in h
    assert "function _drawBrandedField" in h
    assert ("IS_APPAREL||IS_BRANDED" in h) or ("IS_APPAREL || IS_BRANDED" in h)
