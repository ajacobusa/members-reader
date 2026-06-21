# New product departments — Mugs, Calendars, Branded Products

Date: 2026-06-21
Owner: Joffiels (QuoteForge)
Status: design synthesized (from multi-agent blueprint) → awaiting sequencing approval

## Goal

Add three new departments — **Custom Mugs**, **Custom Calendars**, **Custom Branded
Products** — that follow the EXACT same pattern as Wall Art and Apparel: department-gated
storefront, shared design editor (incl. the Layout Studio), Gelato fulfilment with the
placeholder-UID safety guard, margin/leak/monitoring discipline, professional imagery,
and the full safe-deploy loop. Customer-facing copy must never expose a supplier
(`Gelato`/`Printify`/`Printful`) or the marketplace (`Etsy`).

## How a department is wired today (grounded blueprint)

Reverse-engineered from Apparel (all `file:line` verified):

- **Catalog**: `quoteforge/etsy/apparel_catalog.py` — a frozen dataclass + a compact spec
  list expanded by `_build_catalog()`; `build_apparel_variations()` loops product×size×colour,
  builds stable SKUs, reads cost, and prices every variant to clear the 60% margin floor
  (`min_price_for_margin`/`_list_floor`). Price always re-derives from live cost.
- **Storefront**: three nav surfaces (nav link, dept card, deptswitch bar) + a hidden
  `deptXxx` pane holding a `_xxx_section()` builder (faceted filter bar + tiles). `selectDept()`
  gates which pane shows.
- **Editor**: one shared editor switched by a product flag (`IS_APPAREL`); `applyProductChrome()`
  swaps labels/colour-map/print-bound and reveals the Layout Studio panel. `drawArt`,
  the movable print frame, front/back `SIDES`, the proof + rotate, and the **whole Layout
  Studio** (`LAYOUTS`, `drawArcText`, `_drawLayout`, `_decor`, `_drawCollage`) are
  **product-agnostic — they draw into any `{x,y,w,h}` bound**.
- **Gelato**: two-layer SKU→UID map (`GELATO_UID_MAP` + `GELATO_PRODUCT_FAMILY_MAP` via
  env/JSON) resolved by `gelato_variant_resolver`; `TEST_MODE`/missing-key = safe no-op;
  per-department `verify_*_mappings` placeholder guard; `enrich_*_order` ingest seam.
- **Monitoring**: margin/financial/claims/tracking/fulfilment route off generic order
  fields, so they cover a new department once its variations + `enrich_*_order` exist.
- **Leak guard**: `test_customer_copy_no_leak.py` + in-suite brand tests scan the rendered
  page AND the source.

### The 12-step "add a department" recipe (per department)

1. `quoteforge/etsy/<dept>_catalog.py` — dataclass + spec list + `_build_catalog()` +
   `build_<x>_variations()` priced to the floor + `<x>_dimensions_for()`.
2. Resolver/ingest: `parse_/resolve_/enrich_<x>_order` + `verify_<x>_mappings`.
3. Wire `enrich_<x>_order` into `pipeline_orchestrator.py` + `webhook_server.py`.
4. Gelato `(type,tier)` families via env/JSON (TEST_MODE on until a real test order).
5. Storefront data-prep in `build_shop_home` (`<x>_formats_json`, tile photos).
6. `_<x>_section(photos)` builder (from-price, sub-sections, faceted filter, tiles).
7. Nav link + dept card + deptswitch button + `dept<X>` pane.
8. Extend `selectDept()` / `showAllDepartments()`.
9. Editor mode flag/branch in `setProductType`/`applyProductChrome`; `shop<X>` entry;
   reuse `drawArt`/Layout Studio unchanged.
10. `margin_guard` audit loop + `catalog_sync` include for the new kind.
11. `test_<x>_catalog.py` + `test_<x>_storefront.py` + keep `test_customer_copy_no_leak` green.
12. `rebuild-site` → full suite green → safe-deploy → UAT.

## What's reusable now vs net-new

**Reusable for ALL three (≈ the whole stack):** catalog/pricing engine, Gelato mapping +
TEST_MODE safety + placeholder guard, the shared editor, the **Layout Studio** (the requested
"AI design layouts" mostly map onto existing layouts — see per-dept), movable print frame,
front/back sides, clean proof + rotate, faceted filter bar, department shell, margin/claims/
tracking/fulfilment, leak-guard discipline, resolution/contrast/crop checks.

**Net-new (phased, each its own effort) — these do NOT exist even for Apparel:**
- True **360°/orbit** preview (today's "spin" is only a 2-image front/back flip).
- **Flipbook / multi-page** preview (proof is one image per side).
- **12-month calendar engine** (page model + month/date grid + holidays/events).
- **AI auto-concept generation** (layouts are hand-authored templates, not AI-proposed).
- **Scheduled daily Gelato sync** (`catalog_sync.py` exists but runs on-demand only — no cron).
- Mug **cylindrical wrap/panorama unwrap** + handle-break two-panel geometry.
- Branded **step-and-repeat pattern fill**, **per-model phone-case** axis, **bundle/kit** model.

## Per-department first-pass scope

### Custom Mugs (≈ high reuse; some curved geometry net-new)
Categories: Coffee, Ceramic, Accent, Travel, Enamel, Color-Interior, Large-Capacity.
First pass: `mug_catalog.py` (adds `capacity_oz`, `wraps:bool`, `rim_band_px`); 7 product
types × sizes/colours/material/price; reuse Layout Studio for **Center Graphic (freeform/
badge), single-line Wraparound (wrap), Left/Right-Handle panel (front/back sides + chest/
hbanner), Photo Collage (collage), Minimalist (minimal), Typography (street/vstack/hbanner)**;
resolution/contrast/crop checks reused. **Later:** full panoramic cylindrical unwrap + curved
re-projection, true 360 viewer, handle-break auto two-panel, curved safe-area + seam validation.

### Custom Calendars (most net-new — phase honestly)
Categories: Wall, Desk, Family Organizer, Corporate, Photo, Event/Countdown, Business-Promo.
First pass: full catalog/pricing/Gelato/storefront contract is REAL, but the editor proof ships
**Layout A (one photo/month) + a designed cover + ONE representative live month page** (reusing
the single-bound preview) rather than all 12. **Later (in order):** true 12-month page model +
per-page capture/restore + **flipbook** proof; month/date engine (weekday offsets, holidays,
birthdays, custom start dates) + low-res/print-safe validation; AI auto-layout distributing
1–50 photos across months; Family member-column grid + Corporate brand-header + B2B volume
pricing. Honest note: pass-one sells a credible cover+sample-month product; the 12-page/flipbook/
AI-layout value is phased work, not a one-commit copy of Apparel.

### Custom Branded Products (≈ highest reuse — flat bounds)
Categories: Tote, Water Bottle, Tumbler, Mouse Pad, Notebook, Journal, Sticker, Phone Case,
Keychain, Business Gift sets. First pass: `branded_catalog.py`; the **flat-bound** items (tote,
mouse pad, sticker, notebook/journal cover, keychain) use existing rectangular bounds and the
full Layout Studio covers nearly every requested style (Corporate→hbanner, Startup→minimal,
Luxury→monogram, Event→emblem/collage, Trade-show/Promo→badge, Sports/Schools→adventure,
full-wrap→wrap). Logo placement: center/corner/badge/full-wrap already exist; **repeating-pattern
tile** is a small new `_decor`. **Later:** 360 wrap for bottles/tumblers, per-model phone-case
axis + bound table, bundle/kit aggregation (combined price + slowest-item production time).

## Recommended sequence

**Branded → Mugs → Calendars** (reuse-descending, net-new-ascending). Branded's flat-bound
first pass is the cleanest proof that the department pattern generalises to a 3rd department;
Mugs adds curved/wrap concerns; Calendars is the multi-page program. (Open to Mugs-first if you
prefer the flagship — Mugs' first pass is also high-reuse if we ship single-line wrap + panels
and defer the panorama/360.)

## Imagery

Each department gets professional Higgsfield hero + tile + lifestyle images (prompts captured
per department in the workflow output) — generated and owner-approved before launch, externalised
like the existing heroes.

## Risks / discipline

- Storefront is one large generated f-string (hallucination trap): implement **inline with the
  safe-deploy loop**, regenerate + grep the literal after every edit, never parallel-edit the file.
- Keep `TEST_MODE` on; map real Gelato UIDs and pass `verify_<x>_mappings` before going live.
- Every customer-facing string scanned for supplier/marketplace leak.
- Each department first-pass is itself several PRs; ship per the loop with UAT links.
