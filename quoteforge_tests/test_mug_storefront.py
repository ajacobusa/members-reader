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
