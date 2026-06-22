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


def test_calendar_12month_flipbook(tmp_path):
    h = _page(tmp_path)
    assert 'id="mcalbar"' in h and 'id="flipPop"' in h
    assert "function _drawMonthGrid" in h and "function _drawCalPage" in h
    assert "function openFlipbook" in h and "function renderCalSlots" in h
    assert "let CAL_PHOTOS" in h and "function calPhotoUpload" in h
    assert "Preview calendar" in h and "12-month calendar" in h
    assert "gelato" not in h.lower() and "printify" not in h.lower()


def test_calendar_monthly_photos_carried_into_order(tmp_path):
    # REGRESSION: the 12-month intent (year + which months have a photo) must be
    # captured into the saved design AND the basket line, so production receives
    # the monthly photos - not just the cover.
    h = _page(tmp_path)
    assert "function _calMeta" in h and "function _calCount" in h
    # carried into BOTH the design state and the cart line
    assert h.count("cal:_calMeta()") >= 2
    # live "X of 12 months added" counter in the editor
    assert 'id="calcount"' in h and "of 12 months added" in h
    assert "function _updCalCount" in h
    # the final-proof summary shows the monthly count
    assert "monthly photos added" in h
    # copy reconciled to the live 12-month build (no longer cover-only)
    assert "Add a photo for each of the 12 months" in h
    assert "gelato" not in h.lower() and "printify" not in h.lower()


def test_calendar_photos_reset_on_product_open(tmp_path):
    # REGRESSION: opening any product must clear CAL_PHOTOS so a prior calendar's
    # photos never carry into a different calendar/order (privacy + wrong-photo guard).
    h = _page(tmp_path)
    empty = "CAL_PHOTOS=[null,null,null,null,null,null,null,null,null,null,null,null]"
    # appears at declaration AND in the product-open reset (openM)
    assert h.count(empty) >= 2
    assert "Clear any 12-month calendar photos" in h


def test_calendar_grid_two_letter_weekdays(tmp_path):
    # REGRESSION: single-letter S/S and T/T weekday headers are ambiguous; use two.
    h = _page(tmp_path)
    assert "_WD=['Su','Mo','Tu','We','Th','Fr','Sa']" in h


def test_calendar_cover_strips_editor_chrome(tmp_path):
    # REGRESSION: the flipbook cover must not show the editor frame/drag handles.
    h = _page(tmp_path)
    assert "strip editor chrome" in h
