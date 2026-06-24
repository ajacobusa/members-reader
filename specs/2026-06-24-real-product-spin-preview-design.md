# Real-product spin preview — design spec (2026-06-24)

## Goal
The customization preview must look as real as the actual product the customer
receives, and the customer must be able to **rotate the real product they
designed** to review their customization front and back. No separate "3D"
representation that looks different from what ships.

## Source of truth (reuse the existing pipeline — no parallel system)
A single resolver returns, for the product currently in the editor, a mockup
"base" — keyed by the id the editor already carries (apparel `garment_id`,
else `product_id`). Priority order:

1. `brand/mockups/<id>.{png,jpg}` — manual override (already wired) + optional
   `brand/mockups/<id>.json` geometry sidecar.
2. **Existing real photos already in the pipeline:**
   - Apparel: `APPAREL_COLOR_IMG[gid][colour]` (per-colour front) and
     `APPAREL_SIDE_IMG[gid] = {front, back}` — already in the page JS.
   - Mug / branded / calendar: the `tile-<product_id>.jpg` that the
     `product-photos` agent downloads. These exist server-side
     (`_mug_photos` / `_branded_photos` / `_cal_photos`) but today only feed the
     grid tiles. Expose them to the editor JS as new maps `MUG_IMG`,
     `BRANDED_IMG`, `CAL_IMG` (`product_id -> hosted url`).
3. Generated field (today's `_drawMugField` / `drawGarment` / etc.) when no photo
   exists yet — so a half-set-up shop never ships a broken image.

Resolver shape (JS):
```
_mockBase() -> { front, back|null, area:[x,y,w,h frac], cyl:bool, span:float } | null
```
`area`/`cyl`/`span` come from per-product-type defaults, overridable by the
`brand/mockups/<id>.json` sidecar.

## Surfaces (all driven by the one resolver)

### Editor canvas — real photo everywhere
Extend the existing apparel real-photo path in `drawArt` to `IS_MUG` /
`IS_BRANDED` / `IS_CAL`: when a base photo is available, set `#mgarment` to it,
clear the canvas, and composite the design on top inside the **existing draggable
print frame** (`_placeBoundMock`) — the buyer drags/sizes it exactly like a tee.
Gate the generated field draws (`_drawMugField` etc.) on `!_mock`. Falls back to
the generated field when no photo. (Edit flat = precise placement.)

> As-built: the photos are sourced **automatically** from the pipeline
> (`MUG_IMG` / `BRANDED_IMG` / `CAL_IMG` from `tile-<id>.jpg`; apparel from
> `APPAREL_COLOR_IMG` / `APPAREL_SIDE_IMG`); `brand/mockups/` is an override only.
> The apparel colour guard (`hasColor`) is mirrored in `_mockBase` so a
> colour-agnostic side photo never misrepresents a coloured garment.

### Inline spin — the preview IS the product
Remove the separate "View in 3D — spin it" button/modal. The preview itself
rotates via the existing drag gesture (drag the design *inside* its frame to
move/size it; drag the product *outside* the frame to rotate):
- **Mug / bottle / tumbler:** drag spins the real-photo wrap around the barrel
  (design wraps on the curve — "present curved"). Reuses the wrap math from the
  current `_openCylSpin` / `_wrapInto`, now compositing onto the real photo.
- **Apparel:** drag flips between the real **front** and **back** photos, each
  carrying that side's own design (front/back already exist via `APPLACEMENT` +
  `proofFlip`).
- **Flat (poster / tote / calendar):** single face, no spin.
A small "↻ drag to rotate" cue sits on the preview so the affordance is obvious.

### Final review step
Same real-photo + spin, with the curve/wrap realism applied (cylinders) — the
moment that sells. Front/back reachable by the same drag/toggle.

## Geometry
Per-product-type defaults for `area` / `cyl` / `span`; `cyl` inferred from the
product name (mug/bottle/tumbler) unless the sidecar overrides. Owner tunes the
print rectangle per real photo via `brand/mockups/<id>.json`.

## Hard constraints (launch blockers)
- Photos are re-hosted (`_emit`) — never a raw supplier URL; **0** occurrences of
  `gelato` / `printify` / `printful` in `docs/index.html` (existing leak test).
- No marketplace name ("Etsy") in rendered copy.
- Generated fallback when photos absent (TEST_MODE / pre-launch) — never a broken
  image, never a blank product.
- Every change ships with a `# REGRESSION:` test; full suite green before merge.

## Out of scope (YAGNI)
- Live Gelato mockup-render API (async, can't be instant in-browser — confirmed).
- A fullscreen "expand" preview (inline-only, per owner).
- Wall-art (galleries, not per-product photos) — unchanged.

## Affected code
- `quoteforge/etsy/listing_preview.py`: new `MUG_IMG`/`BRANDED_IMG`/`CAL_IMG`
  injection; unified `_mockBase`; `drawArt` real-photo extension; inline-spin
  wiring on the preview; remove the 3D modal/button; keep `_wrapInto` /
  `_drawCylBody` (now fed by `_mockBase`).
- `quoteforge_tests/test_realphoto_mockup.py` (+ mug/apparel storefront tests):
  update for inline spin (no modal), add real-photo-editor + front/back
  regressions.
- `brand/mockups/README.md`: note that the primary source is now the auto
  pipeline; this folder is an override.

## Acceptance
- Mug/bottle/tumbler + apparel previews render on the real photo (when present),
  with the design composited; generated fallback otherwise.
- Dragging the product rotates it: cylinders spin (wrap), apparel flips
  front/back; flat goods don't spin.
- No "View in 3D" modal remains; inline rotate cue present.
- 0 supplier/marketplace leaks; full suite green; visually verified in-browser.
