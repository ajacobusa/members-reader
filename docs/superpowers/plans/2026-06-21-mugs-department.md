# Custom Mugs — Department First Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship a real, sellable "Custom Mugs" department (coffee/ceramic/accent/travel/enamel/colour-interior/large-capacity mugs) following the just-shipped Branded Products pattern, reusing the design editor + Layout Studio, merchandised for gifting.

**Architecture:** A self-contained `mug_catalog.py` (mirrors `branded_catalog.py`) + a storefront `_mug_section` + an `IS_MUG` editor mode reusing `drawArt`/Layout Studio over a **white ceramic print field** (mugs print on the white body; the colour swatch is the handle/interior/rim accent). Net-new (cylindrical panorama/360, handle-break two-panel) deferred per the approved phasing.

**Tech Stack:** Python catalog/pricing, Gelato resolver (TEST_MODE-safe), HTML/Canvas storefront f-string, pytest, Higgsfield imagery, Claude_Preview MCP for live verify.

**THE TEMPLATE IS THE SHIPPED BRANDED DEPARTMENT.** For every task, read the parallel Branded implementation and mirror it, swapping branded→mug data:
- `quoteforge/etsy/branded_catalog.py` → `mug_catalog.py`
- `_branded_section`, `_branded_hero`, `deptBranded`, `selectDept('branded')`, `IS_BRANDED`, `shopBranded`, `_drawBrandedField`, `BRANDED_FORMATS`/`BRANDED_DIMS`/`BRANDED_PID`, `applyBrandedFilters`/`clearBrandedFilters`, `bfCat`/`brandcard`/`brandfilter` → the `mug`/`Mug`/`mg…` equivalents.
- Tests `test_branded_catalog.py` / `test_branded_storefront.py` → `test_mug_catalog.py` / `test_mug_storefront.py`.

**Conventions:** after f-string edits run `python -m quoteforge.admin rebuild-site` and grep `docs/index.html` for the intended literal. No `gelato`/`printify`/`printful`/`etsy` in customer-facing strings. Commit per green task. Branch `feat/mugs-department` already created off main.

**Mug-specific differences from Branded (IMPORTANT):**
1. The editor print field is the **white printable mug body** (a light ceramic tone, ~`#f4f3ef`), NOT the variant colour — because a mug's "colour" is the **handle/interior/rim accent**, while the design prints on the white body. So `_drawMugField` fills light ceramic and the colour swatch represents the accent (kept for the order, shown as a small accent cue). Auto-contrast text therefore stays dark-on-light.
2. Catalog adds `capacity_oz:int` and `wraps:bool` fields (forward-looking for the deferred panorama; `wraps=False` for accent/colour-interior/travel where the handle breaks the wrap).
3. Sizes are capacities (`"11oz"`, `"15oz"`, `"20oz"`, `"12oz"`).

---

## Task 1: mug_catalog.py — products, variants, pricing, dimensions

**Files:** Create `quoteforge/etsy/mug_catalog.py`; Test `quoteforge_tests/test_mug_catalog.py`

- [ ] **Step 1: failing test**

```python
# quoteforge_tests/test_mug_catalog.py
from quoteforge.etsy.mug_catalog import (
    MUG_CATALOG, build_mug_variations, mug_dimensions_for, get_mug)


def test_catalog_has_core_mugs():
    ids = {p.product_id for p in MUG_CATALOG}
    for pid in ("classic_mug", "large_mug", "color_mug", "accent_mug",
                "enamel_mug", "travel_mug", "xl_mug"):
        assert pid in ids, pid


def test_every_variant_clears_the_margin_floor():
    from quoteforge.config import TARGET_MARGIN_PCT
    vs = build_mug_variations()
    assert vs
    for v in vs:
        assert v.price > v.gelato_cost
        assert v.margin_pct >= TARGET_MARGIN_PCT


def test_dimensions_lookup_falls_back_safely():
    assert mug_dimensions_for("classic_mug")[0] > 0
    assert mug_dimensions_for("nope")[0] > 0
```

- [ ] **Step 2: run, verify fail** — `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_mug_catalog.py`

- [ ] **Step 3: create `quoteforge/etsy/mug_catalog.py`** — mirror `branded_catalog.py` exactly (module docstring; `MugProduct` dataclass with the SAME fields as `BrandedProduct` PLUS `capacity_oz: int = 11` and `wraps: bool = True`; `_MUG_TYPES` spec; `_build_catalog`; `MUG_CATALOG`; `MugVariant`; `get_mug`; `mug_dimensions_for`; `_variant_sku`; `_variant_cost`; `_list_floor`; `build_mug_variations`; `mug_skus`). EVERY function/class gets a docstring (the doc ratchet scans this module). The print area is a mug wrap panel; default dims `(2475, 1155)` at 300 DPI. Use this `_MUG_TYPES` (product_id, name, type_name, category, sizes, colors, base_cost, brand, tier, w, h, capacity_oz, wraps):

```python
_MUG_TYPES = [
    ("classic_mug", "Classic Ceramic Mug (11oz)", "Coffee Mug", "Coffee Mugs",
     ["11oz"], ["White", "Black", "Navy", "Red", "Forest Green"],
     7.0, "Gelato Ceramic 11oz", "Value", 2475, 1155, 11, True),
    ("large_mug", "Large Ceramic Mug (15oz)", "Coffee Mug", "Ceramic Mugs",
     ["15oz"], ["White", "Black", "Navy"],
     8.0, "Gelato Ceramic 15oz", "Classic", 2790, 1320, 15, True),
    ("color_mug", "Colour-Interior Mug (11oz)", "Colour-Interior Mug", "Colour-Interior Mugs",
     ["11oz"], ["Black", "Navy", "Red", "Forest Green", "Royal Blue", "Maroon"],
     9.0, "Gelato Colour Mug", "Classic", 2200, 1155, 11, False),
    ("accent_mug", "Accent Mug", "Accent Mug", "Accent Mugs",
     ["11oz", "15oz"], ["Black", "Red", "Navy", "Dusty Rose", "Forest Green"],
     9.0, "Gelato Accent Mug", "Classic", 2200, 1155, 11, False),
    ("enamel_mug", "Enamel Camp Mug (12oz)", "Enamel Mug", "Enamel Mugs",
     ["12oz"], ["White", "Black", "Navy", "Red"],
     11.0, "Gelato Enamel 12oz", "Premium", 2400, 1050, 12, True),
    ("travel_mug", "Stainless Travel Mug (15oz)", "Travel Mug", "Travel Mugs",
     ["15oz"], ["White", "Silver", "Black"],
     13.0, "Gelato Travel 15oz", "Premium", 2600, 1700, 15, False),
    ("xl_mug", "Large-Capacity Mug (20oz)", "Large Mug", "Large-Capacity Mugs",
     ["20oz"], ["White", "Black", "Navy"],
     10.0, "Gelato Ceramic 20oz", "Premium", 3150, 1500, 20, True),
]
```

(All listed colours must exist in the storefront `APPARELCOLOR` hex map — White/Black/Navy/Red/Forest Green/Royal Blue/Maroon/Dusty Rose/Silver are all present after the Branded work; no new swatches needed.)

- [ ] **Step 4: run, verify pass.** - [ ] **Step 5: commit** `feat(mugs): catalog + variants priced to the 60% floor`

---

## Task 2: mug_catalog.py — Gelato ingest seam + guard

Mirror `branded_catalog.py`'s `parse_branded_format`/`branded_sku_for`/`resolve_branded_sku`/`enrich_branded_order`/`verify_branded_mappings` as `parse_mug_format`/`mug_sku_for`/`resolve_mug_sku`/`enrich_mug_order`/`verify_mug_mappings` (product_type `"mug"`). Tests mirror `test_branded_catalog.py`'s round-trip/enrich/verify (use `"Classic Ceramic Mug (11oz) - White"`, `"11oz"` → `GEL-CLASSIC_MUG-11OZ-WHITE`). Every new function gets a docstring. Commit `feat(mugs): Gelato ingest seam + placeholder guard`.

---

## Task 3: wire enrich_mug_order into the pipeline

Add `from quoteforge.etsy.mug_catalog import enrich_mug_order` + the merge call beside `enrich_branded_order` at BOTH sites in `pipeline_orchestrator.py` and `webhook_server.py` (grep `enrich_branded_order` to find them). Test mirrors `test_pipeline_and_webhook_call_branded_enrich`. Commit `feat(mugs): wire enrich_mug_order into order ingest`.

---

## Task 4: margin guard + catalog sync include mugs

Add a `mug` loop in `margin_guard.py` audit (beside the `branded` loop, rows tagged `kind="mug"` from `build_mug_variations()`) and fold `build_mug_variations()` into `catalog_sync.build_local_catalog` (beside branded). Test asserts a `kind=="mug"` row in `audit_catalog()["rows"]`. Commit `feat(mugs): include mugs in margin guard + catalog sync`.

---

## Task 5: storefront `_mug_section` + data-prep + pane

Mirror `_branded_section`/`_branded_hero` as `_mug_section`/`_mug_hero` (faceted filter: Category/Type/Colour/Size; tiles `class="mugcard"` with `data-mpid`/`data-cat`/`data-type`/`data-colors`/`data-sizes` + `onclick="shopMug(name,color)"`; reuse the apparel `apptile/appimg/appcard` CSS by giving tiles `class="appcard mugcard"` and the filter `class="appfilters mugfilter"` — the lesson from Branded). Data-prep: `_mug_photos` (tile-`<pid>`.jpg with SVG fallback), `MUG_FORMATS`, `MUG_DIMS`, `MUG_PID`, and externalize `_mug_hero` via `_save_web_jpg` when `external_assets` (NOT inline — the lesson from Branded). Add the pane `<div id="deptMug" class="deptpane">{_mug_section(_mug_photos)}</div>` after `deptBranded`. Test mirrors `test_branded_section_renders_products_and_facets` (≥7 `data-mpid`, mugfilter, shopMug, MUG_FORMATS/MUG_DIMS, no leak). Commit `feat(mugs): storefront section + data-prep + pane`.

---

## Task 6: department chrome (nav, card, switch, selectDept, filters)

Mirror Branded's chrome: nav link `🍵 Mugs` href=#mugs, dept card `deptmug` (+ `dept_mug_src` prep), deptswitch `.dsmug`, extend `selectDept`/`showAllDepartments` for `'mug'`, and add `applyMugFilters`/`clearMugFilters`. Test mirrors `test_branded_is_a_third_department` (now a FOURTH department; `selectDept(` count ≥ 4). Commit `feat(mugs): department nav, card, switch, pane, filters`.

---

## Task 7: IS_MUG editor mode

Mirror the `IS_BRANDED` editor work. Add `let IS_MUG=false`, `shopMug(name,color)`, extend `setProductType`/`applyProductChrome`/`curFormats`/`renderBg` for `'mug'`, route to `MUG_FORMATS`/`MUG_DIMS`/`MUG_PID`. Widen the shared `IS_APPAREL||IS_BRANDED` print-bound + Layout-Studio branches to also include `||IS_MUG` (grep all `IS_APPAREL||IS_BRANDED` sites). Backdrop: add `function _drawMugField(ctx,x,y,w,h)` that fills a **light ceramic body** (`#f4f3ef`) with a subtle hairline + a small accent stripe in the selected colour at the top (the handle/rim cue) — do NOT fill the whole field with the variant colour (mugs print on white). Branch `drawArt`: `if(IS_MUG)_drawMugField(...); else if(IS_BRANDED)_drawBrandedField(...); else if(IS_APPAREL)drawGarment(...)`. Hide the front/back placement bar for mugs. Test mirrors `test_branded_editor_mode_wired` (`let IS_MUG`, `function shopMug`, `MUG_FORMATS`, `function _drawMugField`, the widened gate). Keep the apparel + branded suites green. LIVE-VERIFY via Claude_Preview (shopMug → badge layout → arc ink on the light field → screenshot). Commit `feat(mugs): editor mode reusing the print frame + Layout Studio`.

---

## Task 8: Higgsfield imagery

Generate (marketing_studio_image, 16:9 hero + 1:1 tiles) a department hero + 7 product tiles in ONE cohesive style (consistent emblem + warm background), matching the Branded look. Save hero → `brand/mugs-hero.jpg` AND `brand/dept-mug.jpg`; tiles → `brand/tile-<pid>.jpg` (classic_mug, large_mug, color_mug, accent_mug, enamel_mug, travel_mug, xl_mug). Rebuild; confirm `assets/tile-classic_mug.jpg` etc. emit to `docs/assets/`. Commit the brand/*.jpg + docs/assets/*.jpg + docs/index.html `feat(mugs): professional Higgsfield hero + product tiles`. (Controller generates these via the Higgsfield MCP, not the subagent.)

---

## Task 9: leak guard + full suite + safe-deploy

- [ ] Leak test `test_mug_no_supplier_leak` (no gelato/printify/printful).
- [ ] Confirm `test_customer_copy_no_leak` + `test_site_doctor` (docs ratchet — every mug_catalog fn documented) + `test_external_assets_lazy_mode` (mug hero externalized) all green.
- [ ] Full suite green — quote the count.
- [ ] Safe-deploy: push, `gh pr create`, merge `--no-ff` to main, `backup-all` + `verify-backup` (HEALTHY), UAT link.

---

## Self-review
- Covers catalog/pricing (T1), Gelato ingest+guard (T2), pipeline (T3), monitoring (T4), storefront+data+pane (T5), chrome (T6), editor reuse with the white-body field (T7), imagery (T8), leak+ratchet+lazy+deploy (T9). Net-new (panorama/360/handle-break) deferred.
- Lessons from Branded baked in: tiles use `appcard mugcard` (inherit tile CSS), hero EXTERNALIZED (not inlined), every catalog fn documented (doc ratchet), apparel count tests already pane-scoped.
- Naming consistency: `MugProduct/MugVariant/MUG_CATALOG/build_mug_variations/mug_dimensions_for/get_mug/parse_mug_format/mug_sku_for/resolve_mug_sku/enrich_mug_order/verify_mug_mappings`; JS `IS_MUG/MUG_FORMATS/MUG_DIMS/MUG_PID/shopMug/_drawMugField/applyMugFilters/clearMugFilters/mugcard/mugfilter/deptMug`.
