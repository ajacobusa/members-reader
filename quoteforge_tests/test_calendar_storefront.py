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


def test_cal_section_renders_products_and_facets(tmp_path):
    h = _page(tmp_path)
    assert 'id="deptCal"' in h
    assert 'class="appcard calcard"' in h
    assert h.count('data-cpid="') >= 7
    assert 'data-cpid="wall_cal"' in h and 'data-cpid="photo_cal"' in h
    assert 'calfilter' in h
    assert 'shopCalendar(' in h
    assert 'CAL_FORMATS' in h and 'CAL_DIMS' in h
    assert "gelato" not in h.lower() and "printify" not in h.lower()


def test_cal_is_a_department(tmp_path):
    h = _page(tmp_path)
    assert 'href="#calendars"' in h
    assert 'deptcal' in h
    assert 'id="deptCal"' in h
    assert "selectDept('cal')" in h
    assert h.count("selectDept(") >= 5
    assert "function applyCalFilters" in h and "function clearCalFilters" in h


def test_cal_editor_mode_wired(tmp_path):
    h = _page(tmp_path)
    assert "let IS_CAL" in h
    assert "function shopCalendar" in h
    assert "CAL_FORMATS" in h and "CAL_DIMS" in h
    assert "function _drawCalField" in h
    assert ("IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL" in h) or ("IS_CAL" in h and "_drawCalField" in h)
