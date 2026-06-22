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
