"""Quick-upload photo REMOVAL: an accidentally-uploaded front/back/sleeve
picture must be removable from its tile - previously the tile filled with the
photo and offered no way back (the buyer was stuck with it on front AND back).
"""
from PIL import Image


def _page(tmp_path) -> str:
    """Render the shop home with the customizer on, same harness as test_ux_editor."""
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    return out.read_text(encoding="utf-8")


def test_every_quick_tile_has_a_remove_control(tmp_path):
    # REGRESSION: each of the four picture tiles carries a remove (✕) control
    # wired to its side; it must stop propagation so tapping ✕ inside the
    # <label> doesn't re-open the file picker.
    h = _page(tmp_path)
    assert "function quickSideRemove" in h
    for side in ("front", "back", "sleeve-left", "sleeve-right"):
        assert f"quickSideRemove('{side}')" in h, side
    assert h.count('class="qdrm"') == 4
    assert "event.preventDefault();event.stopPropagation();" in h


def test_main_page_defines_toast(tmp_path):
    # REGRESSION (found live while verifying the remove control): the MAIN page
    # called toast() 22 times but only the STUDIO template ever defined it -
    # every buyer-feedback message ('design added', 'file too large', 'picture
    # removed') threw ReferenceError silently. The main page must define a
    # self-sufficient toast (creates its own element) plus the visible-state CSS.
    h = _page(tmp_path)
    assert "function toast(" in h
    assert "n=document.createElement('div'); n.id='toast';" in h
    assert "#toast.on{" in h.replace(" ", "")


def test_remove_clears_side_state_thumb_and_input(tmp_path):
    # REGRESSION: removing must clear the SIDE's persisted photo (not just the
    # canvas), reset the tile thumbnail to the ＋, and empty the file input so
    # re-choosing the same file fires onchange again.
    h = _page(tmp_path)
    assert "SIDES[side]=_captureSide();" in h          # persisted after clearing
    assert "th.classList.remove('filled')" in h        # thumb back to ＋
    assert "if(inp) inp.value='';" in h                # same-file re-upload works
    # the ✕ only shows on a FILLED tile
    assert ".qdbox .qdrm{" in h and ".qdbox.hasphoto .qdrm{" in h
