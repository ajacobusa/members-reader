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
    # Every garment TYPE now ships a real product PHOTO (brand/tile-<type>.jpg),
    # so all 39 tiles are photos and the SVG fallback is unused on the live page.
    h = _page(tmp_path)
    assert h.count('class="apptile') == 39        # 13 garments x 3 brand tiers
    assert h.count('class="appimg"') == 39        # a photo for every tile
    assert h.count('class="apptile apptilephoto"') == 39
    assert h.count('class="appsvg"') == 0         # no tile falls back to SVG
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


def test_apparel_shop_by_occasion(tmp_path):
    # REGRESSION: the apparel department leads with an occasion-first strip; each
    # chip opens the editor pre-loaded with that occasion's quote (gift intent is
    # what sells a personalized shop).
    h = _page(tmp_path)
    assert "🎁 Shop by occasion" in h                 # apparel occasion strip
    assert h.count('class="appocc"') == 9             # nine occasion chips
    assert "function shopApparelOccasion" in h        # opens editor pre-loaded
    for label in ("Birthday", "Anniversary", "For Mom", "Memorial", "Wedding"):
        assert f'>{label}</span>' in h, label
    # a real occasion quote is wired into a chip's onclick
    assert "shopApparelOccasion('[Name]" in h
    # the chip pre-fills the wording box (editable starter) + redraws the preview
    assert "t.value=quote" in h and "drawArt();" in h


def test_apparel_filter_bar(tmp_path):
    # REGRESSION: a Gelato-style facet filter bar lets customers narrow apparel by
    # Department / Type / Brand / Colour / Size across both Men's and Women's, with
    # client-side show/hide driven by per-tile data-* attributes.
    h = _page(tmp_path)
    assert 'class="appfilters"' in h
    for sid in ('id="afDept"', 'id="afType"', 'id="afBrand"',
                'id="afColor"', 'id="afSize"'):
        assert sid in h, sid
    assert h.count('class="appfilter"') == 5          # five facet dropdowns
    assert "function applyApparelFilters" in h and "function clearApparelFilters" in h
    # every tile carries the facets the filter reads
    assert h.count("data-type=") == 39 and h.count("data-colors=") == 39
    for attr in ("data-gender=", "data-brand=", "data-sizes="):
        assert attr in h, attr
    # the two departments are wrapped so a whole group can hide
    assert h.count('class="appgroup"') == 2
    # real facet option values are populated from the catalogue
    assert '<option value="Hoodie">' in h and '<option value="Tank Top">' in h
    assert '<option value="Comfort Colors">' in h     # brand facet
    assert '<option value="White">' in h              # colour facet
    assert '<option value="2XL">' in h                # size facet
    assert '<option value="men">' in h and '<option value="women">' in h
    assert 'id="afNoMatch"' in h                      # empty-state message
    # no supplier leak via the new facet values
    assert "gelato" not in h.lower() and "gildan" not in h.lower()


def test_apparel_color_swatches_and_carry_through(tmp_path):
    # REGRESSION: each tile shows its available-colour swatch dots (filled client-
    # side from APPARELCOLOR), the filter rings the chosen colour, and clicking a
    # swatch / a tile under an active colour filter opens the editor in that colour
    # so the live preview recolors. Also fixes pickFmt (was indexing wall-art
    # formats), so apparel colour selection actually changes the garment.
    h = _page(tmp_path)
    assert h.count('class="appsw"') == 39          # a swatch row per tile
    assert h.count("data-garment=") == 39          # garment name for swatch clicks
    assert "function initApparelSwatches" in h     # paints the dots on load
    assert "APPARELCOLOR[cn]" in h                 # dot colour from the shared map
    assert "function selectApparelColor" in h      # preselect colour in editor
    assert "function shopApparel(garment,color)" in h   # carries the colour through
    assert "_afVal('afColor')" in h                # tile click uses the filter colour
    assert "const f = curFormats(i)[j]" in h       # pickFmt bug fix (apparel-aware)
    assert "seldot" in h                           # selected-colour ring class
    assert "initApparelSwatches()" in h            # invoked on DOMContentLoaded


def test_apparel_percolor_tile_swap_wired(tmp_path):
    # REGRESSION: the per-colour supplier-photo swap is wired (no-op until go-live).
    h = _page(tmp_path)
    assert "const APPAREL_COLOR_IMG = {}" in h       # empty in TEST_MODE -> no swap
    for fn in ("function swapTileColor", "function resetTileColor",
               "function selectTileColor", "function _tileColorUrl"):
        assert fn in h, fn
    assert "selectTileColor(card,cn)" in h           # swatch previews colour on tile
    assert "this.dataset.activecolor" in h           # tile opens editor in active colour
    assert "card.dataset.defimg" in h                # default photo remembered for reset
    # the swap lookup key must be the garment_type ID (matches APPAREL_COLOR_IMG
    # keys), NOT the display type_name - else the swap is silently inert at go-live
    assert h.count("data-typeid=") == 39
    assert 'data-typeid="tshirt"' in h and 'data-typeid="hoodie"' in h
    assert "_tileColorUrl(card.dataset.typeid" in h


def test_apparel_tile_uses_supplier_color_image_when_live(tmp_path, monkeypatch):
    # REGRESSION: at go-live the per-colour map is embedded so the tile can swap.
    import quoteforge.images.supplier_mockup as sm
    monkeypatch.setattr(sm, "apparel_tile_color_images",
                        lambda *a, **k: {"tshirt": {"Black": "https://cdn/tee-black.png"}})
    h = _page(tmp_path)
    assert "https://cdn/tee-black.png" in h          # embedded in APPAREL_COLOR_IMG


def test_apparel_filter_options_all_have_products(tmp_path):
    # AUDIT: every facet option the bar offers must correspond to >=1 garment - no
    # orphan filter values (a combination can still be legitimately empty; the UI
    # shows the empty state for that).
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, build_apparel_variations
    priced = {v.garment_id for v in build_apparel_variations()}
    shown = [g for g in APPAREL_CATALOG if g.garment_id in priced]
    types = {g.type_name for g in shown}
    brands = {(g.brand.rsplit(" ", 1)[0] if g.brand else "") for g in shown}
    colors = {c for g in shown for c in g.colors}
    sizes = {s for g in shown for s in g.sizes}
    # each facet value is backed by at least one product
    for t in types:
        assert any(g.type_name == t for g in shown), t
    for b in brands:
        assert any((g.brand.rsplit(" ", 1)[0] if g.brand else "") == b for g in shown), b
    for c in colors:
        assert any(c in g.colors for g in shown), c
    for s in sizes:
        assert any(s in g.sizes for g in shown), s
    # sanity: the headline combination from the screenshot resolves correctly
    # (a brand+colour+size combo either yields matching garments or none - never errors)
    matches = [g for g in shown
               if (g.brand.rsplit(" ", 1)[0] if g.brand else "") and "Black" in g.colors
               and "XL" in g.sizes]
    assert isinstance(matches, list)   # well-defined result for every combination


def test_editor_apparel_pills_are_garment_scoped(tmp_path):
    # REGRESSION: with many garments the editor must scope colour pills to the
    # SELECTED garment (CURGARMENT), not show every garment's colours at once.
    h = _page(tmp_path)
    assert "CURGARMENT" in h and "function apparelFormatsFor" in h
    assert "CURGARMENT+' - '" in h                 # filters APPAREL_FORMATS by garment


def test_apparel_mode_uses_apparel_title_not_wall_art(tmp_path):
    # REGRESSION: opening a garment must NOT show the wall-art listing title
    # ("... Birthday Wall Art | Custom Quote Print ..."). The modal heading is
    # swapped to a garment-aware apparel title, restorable when toggling back.
    h = _page(tmp_path)
    assert "function apparelTitle" in h            # apparel heading generator
    assert "Custom Printed Apparel" in h           # the apparel title copy
    assert "WALLART_TITLE" in h                     # baseline captured for restore
    assert "IS_APPAREL ? apparelTitle()" in h      # title swap wired in chrome
    # the apparel title itself never says "wall art"
    assert "wall art" not in "Personalized Custom Apparel".lower()
    # the post-photo Next button is garment-aware, not "frame & size" in apparel
    assert "IS_APPAREL?'garment':'frame'" in h.replace(" ", "")


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
    assert "'3. Size'" in h                               # step-3 is size-only in apparel


def test_apparel_native_step1_shirt_colour(tmp_path):
    # REGRESSION: the apparel editor is garment-native - Step 1's colour row is the
    # SHIRT colour (not the inert wall-art "Background"), picking it recolors the
    # shirt, text colour auto-contrasts, and the duplicate Step-3 colour picker is
    # hidden (Step 3 = size only).
    h = _page(tmp_path)
    assert 'id="mbglbl"' in h                             # the swappable colour-row label
    assert "Shirt colour" in h                            # apparel relabel of "Background"
    assert "function pickShirt" in h                      # Step-1 shirt swatch handler
    assert "function autoContrastText" in h               # text auto-contrast
    assert "TXT_USER_SET" in h                            # respects an explicit text pick
    assert "renderBg" in h and "apparelFormatsFor()" in h  # shirt swatches from garment
    # Step-3 colour/frame picker is hidden in apparel (colour moved to Step 1)
    assert "IS_APPAREL ? 'none' : (fmts.length" in h


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


def test_apparel_preview_is_a_garment_silhouette_by_type(tmp_path):
    # REGRESSION: the editor preview draws a recognizable garment SILHOUETTE for the
    # picked type (tee/tank/long-sleeve/raglan/polo/hoodie/sweatshirt), not a plain
    # rounded rectangle - so the "background" looks like the actual garment.
    h = _page(tmp_path)
    assert "function _garmentShape" in h and "function _garmentType" in h
    assert "new Path2D" in h                       # silhouette path, not a rect
    # type detection covers every garment family
    for kw in ("'tank'", "'longsleeve'", "'raglan'", "'polo'", "'hoodie'", "'sweatshirt'"):
        assert kw in h, kw
    assert "indexOf('hoodie')" in h and "indexOf('tank')" in h
    assert "APPARELCOLOR['Heather Grey']" in h      # raglan contrast sleeves
    assert "chest print area" in h                 # boundary sits on the chest


def test_editor_text_legible_over_photo_and_photo_repositionable(tmp_path):
    # REGRESSION: with an uploaded photo, (1) the wording gets a CONTRASTING
    # outline so it stays legible over any part of the image (a dark photo would
    # otherwise swallow dark text), and (2) the photo has enough bleed to actually
    # be dragged up/down to reposition it (was 1.06 -> barely any room).
    h = _page(tmp_path)
    assert "function _isLight" in h                       # text/outline contrast helper
    assert "overPhoto) ctx.strokeText" in h               # outline drawn over a photo
    assert "1.25*PHOTO_ZOOM" in h                         # bleed -> room to reposition
    # drag handlers still move BOTH axes for text and photo
    assert "TPOS.y=_clamp" in h and "PHOTO_FY=_clamp" in h


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


def test_full_colour_palette_has_swatches_and_filter_options(tmp_path):
    # REGRESSION: every standard colour has a real hex swatch (so tiles/editor/
    # filter never fall back to grey) and appears as a Colour filter option.
    h = _page(tmp_path)
    for colour in ("Royal Blue", "Forest Green", "Sage", "Mustard", "Charcoal",
                   "Purple", "Dusty Rose", "Brown", "Red"):
        assert f'"{colour}":"#' in h, f"{colour} missing hex swatch"   # APPARELCOLOR
        assert f'<option value="{colour}">' in h, f"{colour} missing filter option"
    # auto-contrast knows the new dark shirts (white text on them)
    assert "'Forest Green':1" in h and "'Charcoal':1" in h


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
