"""Storefront: apparel integrates into the EXISTING picker + design editor.

Apparel must appear as a top-level product type the buyer can switch to (Wall
Art <-> Apparel) without disturbing the working wall-art flow, expose garment
sizes + colours, reuse the same personalization editor, and draw a print-safe
boundary so a customer's own design can't be silently cropped. And - the hard
brand rule - no supplier name may reach the page.
"""
from pathlib import Path

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


# ── Apparel is selectable alongside wall art ─────────────────────

def test_product_type_toggle_present(tmp_path):
    h = _page(tmp_path)
    assert "function setProductType" in h
    assert "Wall Art" in h and "Apparel" in h
    assert "IS_APPAREL" in h                       # the mode flag the editor reads


def test_apparel_formats_data_present(tmp_path):
    h = _page(tmp_path)
    assert "APPAREL_FORMATS" in h
    for garment in ("T-Shirt", "Hoodie", "Sweatshirt"):
        assert garment in h


def test_apparel_sizes_in_sizemap(tmp_path):
    # The same SIZEMAP that drives wall-art sizes carries garment sizes, keyed by
    # the apparel "{garment} - {colour}" format name (mirrors "Framed - Oak").
    h = _page(tmp_path)
    for sz in ("S", "M", "L", "XL", "2XL"):
        assert f'"{sz}"' in h or f"'{sz}'" in h or f">{sz} " in h


# ── Design-your-own: the editor is reused with a print-safe boundary ──

def test_apparel_renders_garment_with_print_boundary(tmp_path):
    h = _page(tmp_path)
    assert "function drawGarment" in h             # apparel preview branch
    assert "prints here" in h.lower()              # the print-safe boundary label
    assert "drawArt" in h                          # same editor canvas reused


def test_apparel_sizing_is_final_note_present(tmp_path):
    # REGRESSION: apparel fit is final under the made-to-order policy; the buyer
    # must be told before ordering, so we don't get "wrong size" exchange demands.
    h = _page(tmp_path)
    assert "mapparelnote" in h
    assert "made to order" in h.lower()
    assert "can't exchange for fit" in h or "cannot exchange for fit" in h


def test_apparel_size_option_has_no_inches_suffix(tmp_path):
    # REGRESSION: garment sizes are S/M/L, not inches - the " in" suffix is
    # suppressed for apparel so the option reads "M - $.." not "M in - $..".
    h = _page(tmp_path)
    assert "IS_APPAREL?'':' in'" in h


def test_apparel_colour_swatches(tmp_path):
    # The pill swatch dot colours apparel pills by garment colour, the same visual
    # cue used for frames - so the picker stays familiar.
    h = _page(tmp_path)
    assert "APPARELCOLOR" in h


# ── Preservation: wall-art path is unchanged + no supplier leak ──

def test_wall_art_picker_still_intact(tmp_path):
    h = _page(tmp_path)
    # the existing format machinery is untouched
    assert "ALL_FORMATS" in h and "function swatchDot" in h
    assert "Poster (unframed)" in h
    # apparel defaults OFF so the working wall-art flow is what loads first
    assert "IS_APPAREL=false" in h.replace(" ", "")


def test_storefront_faq_covers_apparel_and_defects(tmp_path):
    # REGRESSION: the returns/FAQ copy is generalized for apparel (sizing-final
    # note + "defective", not the old "print defect").
    h = _page(tmp_path)
    assert "Apparel sizing" in h
    assert "damaged or defective" in h


def test_no_supplier_name_in_apparel_storefront(tmp_path):
    # REGRESSION: apparel data is emitted from garment/colour/size/price ONLY -
    # never the gelato_sku/gelato_cost fields on the variant.
    h = _page(tmp_path).lower()
    for banned in ("gelato", "printify", "printful"):
        assert banned not in h
