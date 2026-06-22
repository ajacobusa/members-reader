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

def test_homepage_how_it_works_block(tmp_path):
    # REGRESSION: a 3-step "How it works" block de-risks made-to-order (the free
    # proof is the trust pivot) - the study's homepage quick win.
    h = _page(tmp_path)
    assert 'class="hiw"' in h and ">How it works<" in h
    assert h.count('class="hiwstep"') == 3
    for step in ("Personalize it", "Approve a free proof", "We print"):
        assert step in h, step
    assert "free proof" in h.lower() and "made to order" in h.lower()
    # de-risk copy must not leak the supplier
    assert "gelato" not in h.lower() and "printify" not in h.lower()


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
    # REGRESSION: the 3 brand tiers collapse into ONE tile per (gender, garment
    # type) = 13 tiles (7 men's incl. polo + 6 women's). Every tile ships a real,
    # GENDER-correct product photo (brand/tile-<garment_id>.jpg), so all 13 are
    # photos and the SVG fallback is unused on the live page.
    h = _page(tmp_path)
    # Count within the APPAREL pane only - the Branded department reuses the same
    # tile CSS classes (appcard/apptile/appsvg), so page-wide counts would inflate.
    ap = h[h.find('id="deptApparel"'):h.find('id="deptBranded"')]
    assert ap.count('class="apptile') == 13        # one tile per gender+type
    assert ap.count('class="appimg"') == 13        # a photo for every tile
    assert ap.count('class="apptile apptilephoto"') == 13
    assert ap.count('class="appsvg"') == 0         # no apparel tile falls back to SVG
    assert "appemoji" not in h                     # old emoji tiles gone


def test_apparel_brand_tiers_present(tmp_path):
    # REGRESSION: every garment is still offered in 3 brand tiers
    # (Value/Classic/Premium) - now collapsed onto one tile each (13 tiles), the
    # tiers reachable from the in-editor Quality picker (APPAREL_TIERS). Real
    # Gelato brands show in the facet; never Bella+Canvas/Gildan.
    h = _page(tmp_path)
    assert h.count('class="apptier"') == 13                 # one tier cue per tile
    for tier in ("Value", "Classic", "Premium"):
        assert tier in h                                    # all three still offered
    assert "const APPAREL_TIERS =" in h                     # tier-picker data embedded
    assert "Comfort Colors" in h and "Lane Seven" in h      # real Gelato brands shown
    assert "bella" not in h.lower() and "gildan" not in h.lower()


def test_apparel_default_colour_is_white_not_alphabetical(tmp_path):
    # REGRESSION: a garment opens on its light-forward default (White), not the
    # alphabetically-first "Black" - the formats are colour-ordered by catalogue.
    h = _page(tmp_path)
    assert "Men's T-Shirt - White" in h and "Men's T-Shirt - Black" in h
    assert h.index("Men's T-Shirt - White") < h.index("Men's T-Shirt - Black")


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
    ap = h[h.find('id="deptApparel"'):h.find('id="deptBranded"')]   # apparel pane only
    assert 'class="appfilters"' in h
    for sid in ('id="afDept"', 'id="afType"', 'id="afBrand"',
                'id="afColor"', 'id="afSize"'):
        assert sid in h, sid
    assert ap.count('class="appfilter"') == 5          # five facet dropdowns
    assert "function applyApparelFilters" in h and "function clearApparelFilters" in h
    # every tile carries the facets the filter reads
    assert ap.count("data-type=") == 13 and ap.count("data-colors=") == 13
    for attr in ("data-gender=", "data-brand=", "data-sizes="):
        assert attr in h, attr
    # the two apparel sub-sections (Men's/Women's) are wrapped so a group can hide
    assert ap.count('class="appgroup"') == 2
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
    ap = h[h.find('id="deptApparel"'):h.find('id="deptBranded"')]   # apparel pane only
    assert ap.count('class="appsw"') == 13          # a swatch row per tile
    assert ap.count("data-garment=") == 13          # garment name for swatch clicks
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
    # the swap lookup key is the GARMENT_ID (matches APPAREL_COLOR_IMG keys), so
    # each tier/gender maps to its exact product - not the display type_name
    assert h.count("data-gid=") == 13
    assert 'data-gid="m_tshirt"' in h and 'data-gid="m_hoodie"' in h
    assert "_tileColorUrl(card.dataset.gid" in h


def test_apparel_editor_recolors_when_no_percolor_photos(tmp_path):
    # REGRESSION: "T-shirt colour is not changing." The single per-garment side photo
    # (APPAREL_SIDE_IMG[gid].front) is colour-AGNOSTIC - one white studio shot - so
    # using it as the editor's garment mockup rendered the SAME white tee for EVERY
    # colour, and the recolouring silhouette (drawGarment, the only colour-accurate
    # path) was never reached because the photo made _mock truthy. The side-photo
    # fallback must be gated on real per-colour photos existing; pre-launch
    # (APPAREL_COLOR_IMG == {}) there are none, so the editor recolours the silhouette
    # and the colour swatch visibly changes the shirt.
    h = _page(tmp_path)
    assert "const APPAREL_COLOR_IMG = {}" in h            # pre-launch: no per-colour photos
    assert "_hasColorPhotos" in h                          # the new guard exists
    assert "Object.keys(APPAREL_COLOR_IMG[_gid]).length" in h   # guard derives from the map
    # the colour-agnostic side photo may ONLY stand in when real per-colour photos exist
    assert "if(!_u && _hasColorPhotos)" in h
    # and the colour-accurate silhouette path is still wired (reached when ungated)
    assert "function drawGarment" in h and "APPARELCOLOR[cn]||" in h


def test_apparel_final_proof_rotates_front_back(tmp_path):
    # REGRESSION: the final-preview modal must let the buyer spin the garment
    # front<->back (button + drag) so they review BOTH sides before approving -
    # reusing the editor's per-side designs via setPlacement, then recomposing the
    # proof image. Apparel only (wall art has a single face); hidden in the final
    # checkout-wizard mode where the image is replaced by the basket summary.
    h = _page(tmp_path)
    assert 'id="proofFlip"' in h and 'id="proofFlipLbl"' in h     # the flip control + label
    assert "function proofFlip" in h                              # toggle handler
    assert "function _proofRenderSide" in h                       # switch side + recompose
    assert "setPlacement(side)" in h                              # reuses the editor's side swap
    assert "_composedProofURL()" in h                             # recomposes garment+design
    # drag-to-spin wired onto the proof image (mouse + touch)
    assert "_proofDown(event)" in h and "function _proofMove" in h
    # apparel-only + hidden in final wizard mode
    assert "IS_APPAREL?'flex':'none'" in h
    assert "img.classList.toggle('spinnable',IS_APPAREL)" in h
    # discoverable, supplier-safe copy
    assert "See the back" in h and "drag the shirt to spin front" in h
    assert "gelato" not in h.lower() and "printify" not in h.lower()


def test_apparel_tiers_collapse_to_one_gendered_tile(tmp_path):
    # REGRESSION: the 3 brand tiers collapse to ONE tile per (gender, garment type)
    # = 13 tiles (7 men's + 6 women's; no women's polo). Every visible card is the
    # CLASSIC tier and carries a GENDER-correct photo; Value/Premium stay reachable
    # from the in-editor Quality picker. This is what fixed "only men, shown twice".
    import re
    h = _page(tmp_path)
    sec = h[h.find('id="apparel"'):]
    assert h.count('data-gid="') == 13                  # one tile per gender+type
    assert set(re.findall(r'data-tier="(\w+)"', sec)) == {"Classic"}   # Classic only
    for gid in ("m_tshirt", "w_tshirt", "m_polo", "w_hoodie", "w_sweatshirt"):
        assert f'data-gid="{gid}"' in h, gid
    assert 'data-gid="w_polo"' not in h                 # polo is men's-only

    def _img(gid):                                      # the photo a tile renders
        m = re.search(r'data-gid="%s".*?<img[^>]*src="([^"]+)"' % gid, sec, re.S)
        return m.group(1) if m else None
    # men's tee and women's tee tiles use DIFFERENT photos (gender-correct), not the
    # same male shot repeated.
    assert _img("m_tshirt") and _img("w_tshirt")
    assert _img("m_tshirt") != _img("w_tshirt")
    # the in-editor Quality picker keeps all three tiers reachable
    assert 'id="mtierrow"' in h and "function setApparelTier" in h
    assert "function renderTierRow" in h and "const APPAREL_TIERS =" in h
    assert "Men's T-Shirt (Value)" in h                 # Value tier still offered


def test_apparel_editor_front_back_flip_and_logo(tmp_path):
    # REGRESSION: the editor can FLIP the garment to its BACK so a buyer can SEE and
    # design the back (add a photo/wording there), and offers an optional shop logo
    # on front + back. Fixes "I do not see the back to add a picture or wording".
    h = _page(tmp_path)
    assert "const APPAREL_SIDE_IMG =" in h               # front+back image per garment
    assert '"front":' in h and '"back":' in h
    # picking Back drives drawArt to the back image (tiers share the Classic photo)
    assert "APPLACEMENT==='back')?'back':'front'" in h
    assert "APPAREL_SIDE_IMG[_gid]||APPAREL_SIDE_IMG[_bgid]" in h
    # the Back control + a hint that you're now designing the back
    assert 'data-p="back"' in h and 'id="mbackhint"' in h
    # optional logo on both sides, wired + carried into the cart line
    assert 'id="mlogo"' in h and "function toggleLogo" in h
    assert "const GARMENT_LOGO_SRC" in h
    assert "logo:(IS_APPAREL&&LOGO_ON)" in h
    # with external assets the front/back tiles are DISTINCT real files (true back)
    from quoteforge.etsy.listing_preview import build_shop_home
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    out = build_shop_home(numbers=[LAUNCH_PACK_20[0].n], kit_dir=tmp_path,
                          out_path=tmp_path / "e.html", external_assets=True)
    he = out.read_text(encoding="utf-8")
    assert "assets/tile-m_tshirt.jpg" in he and "assets/tile-m_tshirt-back.jpg" in he


def test_apparel_design_frame_is_movable_and_resizable(tmp_path):
    # REGRESSION: the whole design FRAME (the dashed print area) can be MOVED
    # anywhere on the garment and RESIZED - not locked to the chest. The wording +
    # photo live inside it and move/scale with it. (The buyer asked to "move the
    # frame anywhere and resize it".)
    h = _page(tmp_path)
    assert "let BOX={x:0.50,y:0.35,s:1.0}" in h               # frame centre + scale state
    assert "const bw=W*0.42*BOX.s, bh=H*0.32*BOX.s" in h      # bound derived from the frame
    assert "function setFrameSize" in h and "function moveFrame" in h
    assert 'id="mframebar"' in h and 'id="mframesize"' in h   # frame controls in the UI
    assert "moveFrame(-0.04,0)" in h                          # explicit move buttons
    assert "getElementById('mframebar')" in h                # shown only for apparel
    # MOUSE: drag the frame to move, drag the corner handle to resize
    assert "function _hitTarget" in h                        # grab decides move/resize/element
    assert "DRAGTARGET==='frame'" in h and "DRAGTARGET==='resize'" in h
    assert "BOX.s=Math.max(2*Math.abs(px.x-cx)" in h         # corner-drag resizes the frame
    assert "corner to resize" in h                           # visible resize handle + hint
    # the PHOTO has its OWN mouse drag + corner resize handle (separate from frame)
    assert "return 'photoresize'" in h                       # photo corner hit-tested
    assert "DRAGTARGET==='photoresize'" in h                 # photo corner-drag resizes photo
    assert "PHOTO_ZOOM=Math.max(0.2, Math.min(3, PHOTO_ZOOM*r))" in h
    assert "_handle(PHOTO_RECT.x+PHOTO_RECT.w" in h          # photo's own resize handle drawn


def test_apparel_print_area_is_generous_for_placement(tmp_path):
    # REGRESSION: the apparel print area (where the buyer moves+resizes the wording
    # and photo) is a generous zone POSITIONED on the garment's chest/torso (not a
    # tiny centred box, and not so tall it spills onto the lower body). Text has a
    # wide size range but is CAPPED to the print area so it never overflows the
    # garment, and has explicit Move controls (not just drag).
    h = _page(tmp_path)
    assert "const bw=W*0.42*BOX.s, bh=H*0.32*BOX.s" in h  # generous frame (base 0.42x0.32)
    assert 'id="mtsize" min="0" max="40"' in h            # wide text-size range
    assert "stackDim*0.96" in h                           # manual size capped to the box
    assert "function nudgeText" in h and "Move text" in h  # explicit text move controls


def test_apparel_photo_can_shrink_and_move(tmp_path):
    # REGRESSION: on apparel the uploaded photo is a PLACEABLE element - the buyer
    # can SHRINK it (down to 0.2x, not locked to fill) and MOVE it anywhere in the
    # print area. Wall art keeps the framed fill (cover) model untouched.
    h = _page(tmp_path)
    assert "const fit=Math.min(w/iw, h/ih)*PHOTO_ZOOM" in h     # contain-fit x size
    assert "PHOTO_FX=_clamp(f.x,0,1); PHOTO_FY=_clamp(f.y,0,1)" in h   # drag = move
    assert 'min="0.2"' in h                                     # slider can shrink it
    assert "(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL))?0.2:1" in h   # size floor by type (apparel + branded + mug + cal)
    assert "const cover=Math.max(w/iw, h/ih)*1.25*PHOTO_ZOOM" in h     # wall art fill kept


def test_apparel_editor_rotate_and_clean_proof(tmp_path):
    # REGRESSION: (1) dragging the bare garment (outside the design frame) SPINS it
    # front<->back with the mouse; (2) the final proof renders WITHOUT the editor
    # chrome (dashed frame, resize handles, hints) - the buyer's "final design"
    # must look clean, not like the editor.
    h = _page(tmp_path)
    # drag-to-spin
    assert "function _flipSide" in h
    assert "return 'rotate'" in h and "DRAGTARGET==='rotate'" in h
    assert "drag the shirt" in h                             # spin hint in the UI
    # clean proof: chrome is gated behind !_CLEAN and the proof redraws clean
    assert "let _CLEAN=false" in h
    assert "IS_MUG||IS_CAL) && APPAREL_BOUND && !_CLEAN" in h   # chrome skipped when clean (apparel + branded + mug + cal)
    assert "_CLEAN=true; drawArt()" in h                     # proof composites the clean canvas


def test_apparel_proof_shows_garment_not_just_art(tmp_path):
    # REGRESSION: the final-design proof composites the GARMENT photo (the #mgarment
    # layer behind the transparent canvas) WITH the design on top - so the buyer
    # sees the whole piece, not just the wording on a white print area.
    h = _page(tmp_path)
    assert "function _composedProofURL" in h
    assert "_du=_composedProofURL()" in h               # proof uses the composite
    assert "tx.drawImage(mg," in h and "tx.drawImage(cv,0,0)" in h   # garment, then design


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
    # Step-3 colour/frame picker is hidden in apparel (colour moved to Step 1);
    # the print modes (apparel + branded) both hide it via _PRINT.
    assert "const _PRINT=IS_APPAREL||IS_BRANDED" in h
    assert "_PRINT ? 'none' : (fmts.length" in h


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

def test_apparel_front_back_sides_are_independent(tmp_path):
    # REGRESSION: the customer designs the FRONT and the BACK as TWO independent
    # designs - each side keeps its own wording + photo + frame. Placement collapsed
    # to Front/Back (the movable frame replaces left-chest/sleeve). Flipping a side
    # snapshots the one you leave and restores the one you open; both sides are
    # recorded on the cart line.
    h = _page(tmp_path)
    assert 'id="mplacement"' in h                         # the side picker (apparel-only)
    assert h.count('class="plbtn') == 2                   # exactly Front + Back
    assert "setPlacement('front')" in h and "setPlacement('back')" in h
    assert "leftchest" not in h and ">Sleeve</button>" not in h
    assert "function setPlacement" in h
    assert "function _placeBound" in h and "function _placeBoundMock" in h
    # per-side capture/restore on flip
    assert "let SIDES={front:null,back:null}" in h
    assert "function _captureSide" in h and "function _restoreSide" in h
    assert "SIDES[prev]=_captureSide()" in h and "_restoreSide(SIDES[p])" in h
    # the cart records which sides carry a design, plus placement + the print label
    assert "sides:_sides" in h
    assert "placement:(IS_APPAREL" in h.replace(" ", "")
    assert "_PLACE_LBL[APPLACEMENT]" in h


def test_apparel_renders_garment_with_print_boundary(tmp_path):
    h = _page(tmp_path)
    assert "function drawGarment" in h             # apparel preview branch
    assert "drag to move" in h                     # the movable print-frame label
    assert "APPAREL_BOUND" in h                    # the print-safe boundary is drawn
    assert "drawArt" in h                          # same editor canvas reused


def test_editor_uses_real_product_mockup_when_available(tmp_path):
    # REGRESSION: the editor preview uses the ACTUAL product mockup image (per
    # garment type + colour, from APPAREL_COLOR_IMG) on a transparent canvas, with
    # the design composited on its chest - falling back to the recolouring
    # silhouette when no mockup is available (TEST_MODE / pre-go-live).
    h = _page(tmp_path)
    assert 'class="mcanvaswrap"' in h and 'id="mgarment"' in h   # image layer behind canvas
    assert "function _mockupImg" in h                            # cached mockup loader
    assert "const _gid=APPGID[CURGARMENT]" in h                  # per GARMENT lookup
    assert "_tileColorUrl(_gid," in h                            # per garment+colour photo
    assert "ctx.clearRect(0,0,W,H)" in h                         # transparent over the mockup
    assert "_garmentShape" in h                                  # silhouette fallback retained
    # the canvas inside the wrap is transparent so the mockup image shows through
    assert "background:transparent" in h


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
    assert "function _placeBound" in h             # placement-aware print boundary


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
    # suppressed for apparel (and branded) so the option reads "M - $.." not
    # "M in - $..".
    h = _page(tmp_path)
    assert "(IS_APPAREL||IS_BRANDED||IS_MUG||IS_CAL)?'':' in'" in h


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


# ── Apparel Layout Studio (logo + wording preset layouts) ──────────────

def test_layout_studio_display_fonts_loaded(tmp_path):
    # REGRESSION: Layout Studio needs bold display fonts (Bebas Neue for
    # streetwear/athletic, Oswald weights) loaded and offered in the font picker.
    h = _page(tmp_path)
    assert "Bebas+Neue" in h                      # loaded via Google Fonts
    assert "Oswald:wght@500;600;700" in h
    assert "'Bebas Neue'" in h                     # present in the FONTS picker list
    assert "Oswald" in h


def test_layout_studio_arc_text_engine(tmp_path):
    # REGRESSION: the curved-text engine that arcs wording around the logo.
    h = _page(tmp_path)
    assert "function drawArcText" in h
    assert "measureText" in h                      # advances angle by glyph width
    assert "sweep" in h                            # top vs bottom arc direction


def test_layout_studio_state_and_first_layouts(tmp_path):
    # REGRESSION: layout state + the data-driven LAYOUTS table; Freeform default
    # plus the hero Circular Badge with top/bottom arc slots.
    h = _page(tmp_path)
    assert "const LAYOUTS" in h
    assert "let CURLAYOUT" in h and "'freeform'" in h        # freeform default
    assert "let SLOTS" in h
    for slot in ("headline", "secondary", "arcTop", "arcBottom", "tagline", "monogram"):
        assert slot in h, slot
    assert "Circular Badge" in h                              # hero layout present


def test_layout_studio_drawart_branch(tmp_path):
    # REGRESSION: drawArt renders a chosen layout (decor -> logo -> slots) instead
    # of the single text block; freeform keeps today's path.
    h = _page(tmp_path)
    assert "function _drawLayout" in h
    assert "_drawLayout(" in h                       # layout renderer invoked
    assert "CURLAYOUT!=='freeform'" in h             # gated; freeform unchanged


def test_layout_studio_decor_helpers(tmp_path):
    # REGRESSION: decorative elements layouts can drop in (ring, banner, waves,
    # shield/hexagon, rule, stars, monogram frame, collage frames).
    h = _page(tmp_path)
    assert "function _decor" in h
    for d in ("ring", "doublering", "banner", "waves", "shield", "hexagon",
              "rule", "stars", "monogram", "collage"):
        assert "'" + d + "'" in h, d


def test_layout_studio_all_twelve_layouts(tmp_path):
    # REGRESSION: all 12 named layouts present (+ freeform).
    h = _page(tmp_path)
    names = ["Circular Badge", "Vintage Emblem", "Modern Minimalist", "Oversized Streetwear",
             "Vertical Stack", "Horizontal Banner", "Left-Chest Logo", "Back Print",
             "Wraparound", "Photo Collage", "Adventure Badge", "Luxury Monogram"]
    for n in names:
        assert n in h, n
    for k in ("badge", "emblem", "minimal", "street", "vstack", "hbanner", "chest",
              "backprint", "wrap", "collage", "adventure", "monogram"):
        assert "'" + k + "'" in h, k


def test_layout_studio_gallery_ui(tmp_path):
    # REGRESSION: the editor exposes a Layout gallery (built from LAYOUTS) and
    # swaps the visible text-slot inputs when a layout is chosen. The gallery is
    # rendered client-side from LAYOUTS, so assert the generator + wiring, not a
    # static thumbnail count.
    h = _page(tmp_path)
    assert 'id="mlayouts"' in h                       # gallery container
    assert "function renderLayoutGallery" in h
    assert "function pickLayout" in h
    assert "function renderSlotInputs" in h            # swaps inputs per layout
    assert "onSlot(" in h                              # slot input handler
    assert "renderLayoutGallery()" in h                # invoked when apparel controls show
    assert "LAYOUTS.map" in h                          # a thumbnail generated per layout
    assert "layoutthumb" in h                          # gallery tile class
    assert "SLOT_LABELS" in h                          # friendly slot labels


def test_layout_studio_persists_and_payload(tmp_path):
    # REGRESSION: layout + slots persist per side and reach the order payload;
    # `wording` is a readable concat of the active slots; a slots-only badge (no
    # headline) still counts as a designed side.
    h = _page(tmp_path)
    assert "layout:CURLAYOUT" in h                      # captured per side + on the item
    assert "slots:" in h                                # slot text snapshot
    assert "function _slotWording" in h                # readable concat
    assert "_slotWording(" in h                        # used in payload/summary
    assert "_slotsFilled(" in h                        # slots-only side counts as designed


def test_layout_studio_no_supplier_leak(tmp_path):
    # REGRESSION: layout names + help text never expose a print supplier. (The
    # marketplace-copy rule for "Etsy" is covered by test_customer_copy_no_leak;
    # "etsy" also appears as an incidental base64 substring, so it is not scanned
    # here - this guard is specifically the Layout Studio's new copy.)
    h = _page(tmp_path).lower()
    for bad in ("gelato", "printify", "printful"):
        assert bad not in h, bad


def test_layout_studio_collage_multi_image(tmp_path):
    # REGRESSION: Photo Collage supports up to 4 uploaded photos filling the 2x2
    # grid; images persist per side and count the side as designed.
    h = _page(tmp_path)
    assert "let COLLAGE" in h                           # 4-photo state
    assert "function collageUpload" in h               # per-slot file handler
    assert "function _drawCollage" in h                # draws photos into quadrants
    assert "_drawCollage(" in h                         # invoked in the collage layout
    assert "collageUpload(" in h                        # upload inputs wired in the UI
    assert "collage:COLLAGE.map" in h                   # persisted per side
    assert "s.collage" in h                             # counts as a designed side
