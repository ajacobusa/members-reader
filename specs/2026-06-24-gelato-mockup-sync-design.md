# Gelato mockup sync — design spec (2026-06-24)

## Goal
A **fully automated, daily** pipeline that keeps every product's preview matching
the real Gelato product — **all local storage, zero runtime infra** — with a
**checkpoint at every step and an explicit confirmation gate before anything goes
live, for every product**. Nothing un-reviewed ever reaches a customer.

## Pipeline (per the agreed architecture)
```
Gelato → Product Images + printArea → Sync Script → Storage(files) →
Database(metadata) → [rebuild-site] → Personalization Engine → Designer → Final Mockup
```
- **Storage (local, binary):** masters in `brand/mockups/<id>.*`; published web-opt
  copies in `docs/assets/mockups/<id>.jpg` (same-origin; never a `gelato` URL).
- **Database (local, metadata):** `config/mockups.json` — a build-time catalog, NOT
  the orders SQLite.
- **Engine:** `_mockBase()` + `_wrapInto` / `_photoMockupURL` (already built).

## The heart of it: a per-product state machine with checkpoints
Every product (mug / branded / calendar / apparel — **all of them**) advances
through these states. **Each transition is one checkpoint**: it runs a guard, writes
the result to `config/mockups.json`, and only proceeds if the guard passes. A failed
checkpoint stops that product (others continue) and is reported — never silently
skipped.

```
discovered → fetched → validated → geometry_set → rehosted → cataloged
   → READY ──(owner confirms)──▶ approved ──(publish)──▶ PUBLISHED
   any step fails ─▶ error (keeps the last PUBLISHED preview; never breaks the page)
```

| # | Checkpoint | Guard (must pass to advance) | Recorded |
|---|---|---|---|
| 1 | **discovered** | product id has a real Gelato UID (not a `GEL-*` placeholder) | uid |
| 2 | **fetched** | Gelato product/template API returns 200 + an image URL | src url, etag/hash |
| 3 | **validated** | real image bytes · sane dims (≥ min) · **blank-base heuristic** (rejects a mockup that already carries a sample design) · not an error/placeholder | dims, notes |
| 4 | **geometry_set** | `printArea` from Gelato template → mapped to on-photo rect; else type-default (centred; `cyl` for round). Sanity-clamped to 0–1 | area, cyl, span, source=`template\|default\|manual` |
| 5 | **rehosted** | bytes downloaded + saved + web-optimized to `docs/assets/mockups/<id>.jpg` | path, fingerprint(sha256) |
| 6 | **cataloged** | entry written to `config/mockups.json` with all checkpoint results | — |
| 7 | **READY** | all 1–6 ok → awaiting confirmation | — |
| 8 | **approved** | **owner confirmation** (per product or `all`) | approved_by, approved_at |
| 9 | **PUBLISHED** | `live{}` block set from the approved data; baked at next `rebuild-site` | live src+geometry |

**Change detection:** on each daily run, if a product's new image `fingerprint`
differs from its `PUBLISHED` one, it drops back to **READY (pending re-confirm)** —
a changed Gelato image can never auto-replace a live, approved one without a fresh
confirmation. Unchanged + approved products stay PUBLISHED untouched.

## `config/mockups.json` schema (the local "database")
```json
{
  "version": 1,
  "updated_utc": "<stamped after the run>",
  "products": {
    "classic_mug": {
      "category": "mug",
      "gelato_uid": "abc123",
      "status": "ready",                       // discovered|fetched|validated|ready|approved|published|error|skipped
      "checkpoints": {
        "discovered": {"ok": true,  "at": "..."},
        "fetched":    {"ok": true,  "src": "<gelato url>", "at": "..."},
        "validated":  {"ok": true,  "dims": [1200, 1200], "notes": "blank ok", "at": "..."},
        "geometry":   {"ok": true,  "area": [0.30,0.34,0.40,0.34], "cyl": true, "span": 1.9, "source": "template", "at": "..."},
        "rehosted":   {"ok": true,  "path": "assets/mockups/classic_mug.jpg", "fingerprint": "<sha256>", "at": "..."},
        "cataloged":  {"ok": true,  "at": "..."}
      },
      "approved": false, "approved_by": null, "approved_at": null,
      "live": null                              // {src, area, cyl, span} — set ONLY on publish
    }
  }
}
```
`_mockBase()` (and the build) read **only the `live{}` block** — so the storefront
shows a product's real photo strictly after it's been confirmed and published.

## Commands (admin CLI) + the daily agent
- `admin mockup-sync` — runs checkpoints 1–6 for **all products**, updates
  `config/mockups.json`, **emails a per-product review** (READY / changed / error /
  unchanged) with thumbnails. Never publishes.
- `admin mockup-review` — prints the per-product checkpoint table (what passed,
  what's pending confirmation, what errored).
- `admin mockup-approve <id | all>` — the **confirmation gate**: marks products
  approved and copies their data into `live{}`.
- `admin mockup-publish` — `rebuild-site` using only `live{}` blocks, then the
  normal commit/push/UAT.
- **Daily agent `gelato-mockup-sync`** (reuses the existing scheduler cadence,
  07:xx): runs `mockup-sync` + the review email. It does **not** auto-publish.
  Optional `--auto-publish-approved` flag (off by default) lets you, once you trust
  it, auto-publish products that are *already approved and only had an unchanged
  image* — anything new or changed still waits for your confirmation.

## Safety invariants (launch-blockers)
- **No supplier leak:** images re-hosted same-origin; `config/mockups.json` stores
  the Gelato url only under `checkpoints.fetched.src` (internal, never emitted to
  the page). The page still greps clean for `gelato/printify/printful`.
- **No-op until live:** all of 1–9 short-circuit when `TEST_MODE` or no
  `GELATO_API_KEY` or a placeholder UID — the generated preview shows; nothing
  errors.
- **Never auto-publish the unconfirmed:** a product reaches a customer only via the
  explicit `approved → published` confirmation. New/changed images always re-queue.
- **Never break the build:** any per-product failure keeps that product's last good
  `live{}` (or the generated fallback); the agent reports it and moves on.
- **Idempotent + resumable:** re-running picks up from each product's recorded
  state; the fetch cache (`gelato_blank_image`) avoids re-hitting the API.

## Wiring
- `images/supplier_mockup.py`: add `gelato_product_mockup(uid)` (image) and
  `gelato_template_printarea(uid)` (placement) — extend the existing
  product-API client; both key-gated + cached.
- New `automation/mockup_sync.py`: the checkpoint engine over `config/mockups.json`.
- `admin.py`: the four `mockup-*` commands.
- `etsy/listing_preview.py`: `_mockBase()` reads `config/mockups.json` `live{}` (it
  already consumes the `brand/mockups/` manifest — same shape).
- `AUTOMATION_AGENTS.md` + scheduler: register `gelato-mockup-sync` daily.

## Acceptance
- Every product family resolves a base mockup when live + approved; generated
  fallback otherwise.
- Each step writes a checkpoint; `mockup-review` shows the full per-product trail.
- No product publishes without an `approved` confirmation; a changed Gelato image
  re-queues for confirmation.
- 0 supplier/marketplace leaks; full suite green; each new unit has a regression
  test.

## Out of scope (YAGNI for now)
- Cloud storage / CDN / dynamic backend (explicitly local + static).
- Per-design async Gelato mockup rendering (we composite client-side on the blank).
- Auto-mapping for products that aren't Gelato templates → type-default geometry +
  optional one-time manual calibration (then automatic forever).
