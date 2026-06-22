# Custom Calendars — Department First Pass (Cover Designer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Ship a real, sellable "Custom Calendars" department (wall / desk / family / corporate / photo / event / promotional calendars) following the shipped Branded + Mugs pattern. First pass = full catalog/pricing/fulfillment/storefront/imagery + a working **cover designer** (reuses the Layout Studio on a **portrait white-paper field**). The true 12-month page engine, per-month photo upload, and flipbook preview are the labelled NEXT PHASE (deferred).

**Architecture:** Self-contained `calendar_catalog.py` (mirrors `mug_catalog.py`) + a storefront `_cal_section` + an `IS_CAL` editor mode reusing `drawArt`/Layout Studio over a portrait white paper field (calendars print dark-on-white like mugs). **THE TEMPLATES ARE THE SHIPPED MUG + BRANDED DEPARTMENTS** — mirror them, swapping mug→cal data.

**Conventions:** after f-string edits `python -m quoteforge.admin rebuild-site` + grep docs/index.html for the literal. No `gelato`/`printify`/`printful`/`etsy` in customer-facing strings. EVERY catalog fn/class gets a docstring (doc ratchet). Tiles use `class="appcard calcard"` (inherit CSS); hero EXTERNALIZED via `_save_web_jpg` (not inlined). Commit per green task. Branch `feat/calendars-department` already created.

**Calendar-specific notes:**
1. Field is a **portrait white paper** (calendars are portrait, printed dark-on-white). `_drawCalField` fills `#fbfaf7` (paper) with a hairline border + a thin spiral-binding cue along the top. Auto-contrast text dark (extend the `IS_MUG` dark-text rule in `autoContrastText` to also fire for `IS_CAL`).
2. Sizes are paper formats (`"A3"`, `"A4"`, `"A5"`, `"A6"`); colours are `["White"]` (paper) — single-colour, like the mouse pad. The dims are PORTRAIT.
3. Customer copy frames the editor as designing the **calendar cover** (months are arranged after approval / a coming feature) — do NOT overpromise a live 12-month editor.

---

## Task 1: calendar_catalog.py — products, variants, pricing, dimensions

Create `quoteforge/etsy/calendar_catalog.py` mirroring `mug_catalog.py` (module + `CalendarProduct` dataclass with the SAME fields as MugProduct minus capacity_oz/wraps PLUS `pages: int = 13` and `binding: str = "coil"`; `_CAL_TYPES` spec; `_build_catalog`; `CALENDAR_CATALOG`; `CalendarVariant`; `get_calendar`; `calendar_dimensions_for`; `_variant_sku`; `_variant_cost`; `_list_floor`; `build_calendar_variations`; `calendar_skus`). EVERY fn/class documented. Portrait default dims `(2480, 3508)`. Use this `_CAL_TYPES` (product_id, name, type_name, category, sizes, colors, base_cost, brand, tier, w, h, pages, binding):

```python
_CAL_TYPES = [
    ("wall_cal", "Wall Calendar", "Wall Calendar", "Wall Calendars",
     ["A3", "A4"], ["White"], 9.0, "Gelato Wall Calendar", "Premium", 2480, 3508, 13, "coil"),
    ("desk_cal", "Desk Calendar", "Desk Calendar", "Desk Calendars",
     ["A5"], ["White"], 7.0, "Gelato Desk Calendar", "Classic", 2480, 1748, 13, "wire-o"),
    ("family_cal", "Family Organizer Calendar", "Family Calendar", "Family Calendars",
     ["A3"], ["White"], 10.0, "Gelato Family Calendar", "Premium", 2480, 3508, 13, "coil"),
    ("corporate_cal", "Corporate Branded Calendar", "Corporate Calendar", "Corporate Calendars",
     ["A3", "A4"], ["White"], 10.0, "Gelato Corporate Calendar", "Premium", 2480, 3508, 13, "coil"),
    ("photo_cal", "Photo Calendar", "Photo Calendar", "Photo Calendars",
     ["A4"], ["White"], 8.0, "Gelato Photo Calendar", "Classic", 2480, 3508, 13, "coil"),
    ("event_cal", "Event & Countdown Calendar", "Event Calendar", "Event Calendars",
     ["A6"], ["White"], 6.0, "Gelato Event Calendar", "Classic", 1748, 2480, 13, "wire-o"),
    ("promo_cal", "Business Promotional Calendar", "Promotional Calendar", "Business-Promotional Calendars",
     ["A4"], ["White"], 8.0, "Gelato Promo Calendar", "Classic", 2480, 3508, 13, "coil"),
]
```

Tests `quoteforge_tests/test_calendar_catalog.py` mirror `test_mug_catalog.py` (ids include wall_cal/desk_cal/photo_cal/event_cal; every variant clears the floor; dims fallback). Commit `feat(calendars): catalog + variants priced to the 60% floor`.

---

## Task 2: ingest seam + guard

Mirror mug's `parse_mug_format`/`mug_sku_for`/`resolve_mug_sku`/`enrich_mug_order`/`verify_mug_mappings` as the `calendar`/`cal` equivalents (product_type `"calendar"`). Docstrings on all. Tests use `"Wall Calendar - White"`, `"A3"` → `GEL-WALL_CAL-A3-WHITE`. Commit `feat(calendars): Gelato ingest seam + placeholder guard`.

---

## Task 3: wire enrich_calendar_order into pipeline + webhook

Add beside `enrich_mug_order` at both sites. Test mirrors. Commit `feat(calendars): wire enrich_calendar_order into order ingest`.

---

## Task 4: margin guard + catalog sync

Add a `calendar` loop in `margin_guard.audit_catalog` (beside mug, kind="calendar") + fold `build_calendar_variations()` into `catalog_sync.build_local_catalog` (type:"calendar"). Test asserts a `kind=="calendar"` row. Commit `feat(calendars): include calendars in margin guard + catalog sync`.

---

## Task 5: storefront `_cal_section` + data-prep + pane

Mirror `_mug_section`/`_mug_hero` as `_cal_section`/`_cal_hero` (filter Category/Type/Size; tiles `class="appcard calcard"` `data-cpid`/`data-cat`/`data-type`/`data-colors`/`data-sizes` + `onclick="shopCalendar(name,color)"`; externalized hero `cal-hero.jpg`). Data-prep `_cal_photos`/`cal_formats_json`/`cal_dims_json`/`cal_pid_json` → `const CAL_FORMATS/CAL_DIMS/CAL_PID`. Pane `<div id="deptCal" class="deptpane">{_cal_section(_cal_photos)}</div>` after deptMug. Test mirrors mug's section test (≥7 `data-cpid`, calfilter, shopCalendar, CAL_FORMATS/CAL_DIMS, no leak, lazy-mode green). Commit `feat(calendars): storefront section + data-prep + pane`.

---

## Task 6: department chrome (5th department)

Mirror mug chrome: nav `📅 Calendars` href=#calendars, dept card `deptcal` (+ `dept_cal_src`), deptswitch `.dscal`, extend `selectDept`/`showAllDepartments` for `'cal'`, add `applyCalFilters`/`clearCalFilters`. Test: `selectDept(` count ≥ 5. Commit `feat(calendars): department nav, card, switch, pane, filters`.

---

## Task 7: IS_CAL editor mode (cover designer)

Mirror IS_MUG. Add `let IS_CAL=false`, `shopCalendar(name,color)`, extend `setProductType`/`applyProductChrome`/`curFormats`/`renderBg` for `'cal'`, route to `CAL_FORMATS`/`CAL_DIMS`/`CAL_PID`. Widen all `IS_APPAREL||IS_BRANDED||IS_MUG` gates to also include `||IS_CAL` (grep them). Backdrop `function _drawCalField(ctx,x,y,w,h)`: fill `#fbfaf7` paper, hairline border, + a thin dashed spiral-binding cue along the TOP edge (small circles or a dotted line). drawArt branch: `if(IS_CAL)_drawCalField; else if(IS_MUG)_drawMugField; else if(IS_BRANDED)_drawBrandedField; else if(IS_APPAREL)drawGarment`. Extend the `autoContrastText` mug dark-text early-return to also fire for `IS_CAL` (white paper → dark text). Hide front/back placement. Swap chrome labels (title, step-3 "Size", colour-row "Paper", a calendar availability/about line that frames it as designing the **cover**). Test mirrors mug editor test (`let IS_CAL`, `function shopCalendar`, `CAL_FORMATS`, `function _drawCalField`, widened gate). Keep apparel+branded+mug suites green. LIVE-VERIFY (shopCalendar → badge cover → dark arc ink on paper → screenshot). Commit `feat(calendars): cover-designer editor mode reusing the Layout Studio`.

---

## Task 8: Higgsfield imagery

Controller generates (Higgsfield) a hero + 7 calendar tiles in the cohesive sunrise-emblem style. Save hero → `brand/cal-hero.jpg` + `brand/dept-cal.jpg`; tiles → `brand/tile-<pid>.jpg`. Rebuild; confirm assets emit. Commit `feat(calendars): professional Higgsfield hero + product tiles`.

---

## Task 9: leak guard + full suite + deploy

Leak test `test_calendar_no_supplier_leak`; confirm docs-ratchet + lazy-mode + copy-no-leak green; full suite green (quote count); safe-deploy (push → PR → merge --no-ff → backup-all + verify-backup HEALTHY → UAT link).

---

## Self-review
Covers catalog/pricing (T1), ingest+guard (T2), pipeline (T3), monitoring (T4), storefront+pane (T5), chrome (T6), cover-designer editor with portrait white-paper field (T7), imagery (T8), leak+ratchet+lazy+deploy (T9). 12-month page engine + per-month upload + flipbook explicitly DEFERRED (labelled next phase). Lessons baked in: `appcard calcard`, externalized hero, docstrings, dark-on-paper auto-contrast. Naming: `CalendarProduct/CalendarVariant/CALENDAR_CATALOG/build_calendar_variations/calendar_dimensions_for/get_calendar/parse_calendar_format/calendar_sku_for/resolve_calendar_sku/enrich_calendar_order/verify_calendar_mappings`; JS `IS_CAL/CAL_FORMATS/CAL_DIMS/CAL_PID/shopCalendar/_drawCalField/applyCalFilters/clearCalFilters/calcard/calfilter/deptCal`.
