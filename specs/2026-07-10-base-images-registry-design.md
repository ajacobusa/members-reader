# Base Images — named, updatable, colour-verified product photos

**Date:** 2026-07-10 · **Owner approved:** yes (chat) · **Branch:** `feat/base-images-registry`

## Problem

The editor/spin/tiles can already show a REAL product photo per colour
(`APPAREL_COLOR_IMG`), but off-live that map is empty: there is no local,
owner-updatable source of per-colour photos, the photo-colour census is
hardcoded in `listing_preview.py` (`_PHOTO_COLOR`), and nothing verifies that a
photo's colour is one Gelato can actually fulfil.

## Design

### 1. The concept: a *base image*

The real product photo a colour composites on. Named
`base-<garment_id>-<colour-slug>[-back].<ext>` (e.g. `base-m_hoodie-navy.jpg`),
stored in `brand/` (same dir the existing tile photos live in, same `_emit`
same-origin re-hosting).

### 2. The registry: `config/base_images.json` (source of truth)

Env-overridable via `BASE_IMAGES_FILE` (tests), mirroring `MOCKUP_CATALOG_FILE`.
Schema:

```json
{"version": 1, "images": [
  {"garment_id": "m_hoodie", "color": "White", "side": "front",
   "file": "brand/tile-m_hoodie.jpg", "source": "dashboard_export",
   "added": "2026-07-10"}
]}
```

Seeded with today's 26 photos (13 front + 13 back) and the eyeball-verified
census: 10 garments White, `w_tshirt` Heather Grey, raglans `color: ""`
(two-tone, never colour-matched). Seeds point at the existing `brand/tile-*`
files; new installs use the `base-*` naming.

### 3. Build integration (`listing_preview.py` + new `quoteforge/images/base_images.py`)

- `base_images.py`: `load_registry()`, `photo_color(gid, side)`,
  `percolor_files()` → `{gid: {color: path}}`, validation helpers.
- `_PHOTO_COLOR` hardcode is REPLACED by the registry (fallback `""` = never
  match — safe for unregistered garments).
- `APPAREL_COLOR_IMG` is populated from registry per-colour FRONT entries
  (re-hosted), then the live API map (`apparel_tile_color_images`) overlays it
  when live — API wins per colour at go-live.

### 4. Honesty tightening (required by partial per-colour coverage)

Today `drawArt`/`_mockBase` let the colour-agnostic side photo stand in for ANY
colour once `_hasColorPhotos` is true. With incremental dashboard exports that
re-introduces the "white photo for a Navy pick" bug the moment the first Navy
photo lands (Sand would show the white photo). The FRONT stand-in becomes
colour-exact: per-colour URL for its own colour, side photo ONLY on
`_photoColorMatch`. The BACK keeps its existing semantics (side back photo when
per-colour photos exist or the colour matches).

### 5. Operator CLI: `admin base-images`

- `status` — per garment × catalogue colour grid: Gelato-real? (backed by a
  real approved UID via `fulfillable_apparel_facets`) × base image present?
  Plus drift warnings (registry colour no longer Gelato-real, missing file).
  This is the owner's dashboard-export shopping list.
- `add <file> --garment <gid> --colour <name> [--back] [--force]` — validates
  (decodes, min 600px, garment exists, colour in catalogue AND Gelato-real, no
  duplicate unless `--force`), copies to `brand/base-...`, appends registry.
  Rejections state the exact reason. No fabrication: the only accepted source
  is a file the owner supplies.

### 6. Daily guards (`infra_check`)

- **#87 base-image registry integrity:** every entry's file exists + decodes,
  colour ∈ the garment's catalogue colours, and (when the family is UID-mapped)
  colour is Gelato-real. Registry parse failure = red.
- **#88 build parity:** every registered per-colour FRONT for a fulfillable
  garment appears in the built page's `APPAREL_COLOR_IMG`; the built
  `APPAREL_SIDE_IMG` colour metadata equals the registry census.

### 7. Tests (grounded end-to-end)

`quoteforge_tests/test_base_images.py`:
- registry loads + seed census parity (m_hoodie White, w_tshirt Heather Grey,
  raglans "").
- E2E owner flow in tmp dirs: `add` a Navy base image → build → page's
  `APPAREL_COLOR_IMG` has Navy → editor gate serves it; **Sand (uncovered)
  still falls to the silhouette — the partial-coverage honesty pin.**
- `add` rejects: non-Gelato colour, unknown garment, undecodable/small file.
- invariants #87/#88 green on the real repo.
- existing no-leak + recolour pins keep passing.

## Alternatives considered

Extending `config/product_image_overrides.csv` (per-SKU rows, already consumed
by `apparel_tile_color_images`) — fewer new pieces but the wrong grain (one row
per size), no colour verification, no readable registry. Rejected.

## Out of scope

Fabricated/tinted photos; mug/branded/calendar per-colour (single-colour
products); moving the default wording-frame position on model shots (separate
owner-directed polish item).
