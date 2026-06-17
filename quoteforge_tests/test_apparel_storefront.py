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

def test_two_departments_wall_art_and_apparel(tmp_path):
    # REGRESSION: the store is organized into TWO co-equal departments - Wall Art
    # and Apparel - with a "Shop by department" chooser and a nav link + anchor
    # for each, so apparel is a real department, not buried in the editor.
    h = _page(tmp_path)
    assert "Shop by department" in h
    assert "deptcard" in h and "deptwall" in h and "deptapp" in h
    # both department anchors + nav links
    for anchor in ('id="wallart"', 'id="apparel"', 'href="#wallart"', 'href="#apparel"'):
        assert anchor in h, anchor
    assert "Wall Art" in h and "Apparel" in h
    # departments use real lifestyle PHOTOS (not emoji), in a body block
    assert "deptimg" in h and "deptbody" in h


def test_apparel_department_has_mens_and_womens_sections(tmp_path):
    # REGRESSION: the Apparel department is split into Men's / Women's like Gelato's
    # catalogue, each with garment tiles + a design CTA.
    h = _page(tmp_path)
    assert "Custom Apparel" in h
    assert "Men's Clothing" in h and "Women's Apparel" in h
    assert h.count('class="appghead"') == 2       # the two gender sub-sections
    for garment in ("T-Shirt", "Tank Top", "Hoodie", "Sweatshirt", "Polo"):
        assert garment in h                        # the broader Gelato range
    assert "function shopApparel" in h            # opens the editor in apparel mode
    assert "Design yours" in h                    # the per-garment CTA


def test_apparel_cards_use_photos_with_svg_fallback(tmp_path):
    # REGRESSION: full gendered + 3-tier range (13 garments x 3 tiers = 39 tiles).
    # Real PHOTOS for the 3 core types (x2 genders x3 tiers = 18); SVG for the rest.
    h = _page(tmp_path)
    assert h.count('class="apptile') == 39        # 13 garments x 3 brand tiers
    assert h.count('class="appimg"') == 18        # photo for the 3 core types
    assert h.count('class="apptile apptilephoto"') == 18
    assert h.count('class="appsvg"') == 21        # SVG fallback for the rest
    assert "appemoji" not in h                     # old emoji tiles gone


def test_apparel_brand_tiers_present(tmp_path):
    # REGRESSION: each garment is offered in 3 brand tiers (Value/Classic/Premium)
    # with the Gelato brand shown - never Bella+Canvas/Gildan.
    h = _page(tmp_path)
    assert h.count('class="apptier"') == 39
    for tier in ("Value", "Classic", "Premium"):
        assert tier in h
    assert "Comfort Colors" in h and "Lane Seven" in h     # real Gelato brands shown
    assert "bella" not in h.lower() and "gildan" not in h.lower()


def test_editor_apparel_pills_are_garment_scoped(tmp_path):
    # REGRESSION: with many garments the editor must scope colour pills to the
    # SELECTED garment (CURGARMENT), not show every garment's colours at once.
    h = _page(tmp_path)
    assert "CURGARMENT" in h and "function apparelFormatsFor" in h
    assert "CURGARMENT+' - '" in h                 # filters APPAREL_FORMATS by garment


def test_apparel_mode_swaps_wall_art_editor_chrome(tmp_path):
    # REGRESSION: in Apparel mode the editor must hide wall-art-only chrome (room
    # wall colours + tip) and swap the "available as" line, "about" description,
    # step-3 label and price - an apparel buyer never sees poster/frame copy.
    h = _page(tmp_path)
    assert "function applyProductChrome" in h
    for el in ('id="mwallrow"', 'id="mwalltip"', 'id="mavail"', 'id="e3lbl"'):
        assert el in h, el
    # apparel-specific copy is wired in
    assert "T-Shirt, Hoodie or Sweatshirt" in h          # apparel availability line
    assert "made to order just for you" in h             # apparel about-copy
    assert "Garment & size" in h                          # apparel step-3 label


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


def test_wrong_brands_never_on_storefront(tmp_path):
    # REGRESSION: real Gelato brands now render (the tier value-prop), but the
    # WRONG brands (Bella+Canvas / Gildan, which Gelato doesn't carry) must never.
    h = _page(tmp_path).lower()
    assert "bella" not in h and "gildan" not in h


def test_no_supplier_name_in_apparel_storefront(tmp_path):
    # REGRESSION: apparel data is emitted from garment/colour/size/price ONLY -
    # never the gelato_sku/gelato_cost fields on the variant.
    h = _page(tmp_path).lower()
    for banned in ("gelato", "printify", "printful"):
        assert banned not in h
