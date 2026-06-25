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
   → READY ──(TWO AGENTS agree)──▶ confirmed ──(publish)──▶ PUBLISHED
   any step fails ─▶ error (keeps the last PUBLISHED preview; never breaks the page)
```

**The confirmation is automated by two agents** (not a manual owner click). A READY
product is confirmed only when BOTH agree:
- **`gelato-mockup-reviewer`** → **PASS** — the synced image is a clean, **blank**,
  front-on base, and the derived print geometry sits on the real print zone.
- **`gelato-sku-image-match`** → **MATCH** — the SKU resolves to a real (non-placeholder)
  Gelato UID, the image's provenance is that same UID, and the picture is the
  product type/variant the SKU claims.

`confirmed = PASS && MATCH`. If either is HOLD/MISMATCH → the product stays at
`held`, keeps its previous/generated preview, and goes into the daily report for a
human. Both agent verdicts are stored on the product (`review`, `match`) so the
trail is auditable. A human can still override (force-approve / force-hold), but the
**default path needs no human** — the agents are the confirmation.

| # | Checkpoint | Guard (must pass to advance) | Recorded |
|---|---|---|---|
| 1 | **discovered** | product id has a real Gelato UID (not a `GEL-*` placeholder) | uid |
| 2 | **fetched** | Gelato product/template API returns 200 + an image URL | src url, etag/hash |
| 3 | **validated** | real image bytes · sane dims (≥ min) · **blank-base heuristic** (rejects a mockup that already carries a sample design) · not an error/placeholder | dims, notes |
| 4 | **geometry_set** | `printArea` from Gelato template → mapped to on-photo rect; else type-default (centred; `cyl` for round). Sanity-clamped to 0–1 | area, cyl, span, source=`template\|default\|manual` |
| 5 | **rehosted** | bytes downloaded + saved + web-optimized to `docs/assets/mockups/<id>.jpg` | path, fingerprint(sha256) |
| 6 | **cataloged** | entry written to `config/mockups.json` with all checkpoint results | — |
| 7 | **READY** | all 1–6 ok → goes to the two confirming agents | — |
| 8a | **reviewed** | `gelato-mockup-reviewer` → **PASS** (blank base, front-on, geometry on the print zone) | review verdict + reasons |
| 8b | **matched** | `gelato-sku-image-match` → **MATCH** (real UID, provenance, right product type/variant) | match verdict + reasons |
| 8 | **confirmed** | `reviewed.PASS && matched.MATCH` (else → `held`, into the daily report) | confirmed_at, by=`agents` |
| 9 | **PUBLISHED** | `live{}` set from the confirmed data; baked at next `rebuild-site` | live src+geometry |

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
      "review": {"verdict": null, "reasons": null, "at": null},   // gelato-mockup-reviewer: PASS|HOLD
      "match":  {"verdict": null, "reasons": null, "at": null},   // gelato-sku-image-match: MATCH|MISMATCH
      "confirmed": false, "confirmed_by": "agents", "confirmed_at": null,
      "live": null                              // {src, area, cyl, span} — set ONLY on publish after confirm
    }
  }
}
```
`_mockBase()` (and the build) read **only the `live{}` block** — so the storefront
shows a product's real photo strictly after it's been confirmed and published.

## Commands (admin CLI) + the daily agent
- `admin mockup-sync` — runs checkpoints 1–6 for **all products** (fetch / validate
  / geometry / re-host / catalog), writing each to `config/mockups.json`; READY
  products are queued for the two confirming agents. Never publishes.
- `admin mockup-confirm` — runs the **two agents** over every READY product
  (`gelato-mockup-reviewer` + `gelato-sku-image-match`), writes both verdicts, and
  sets `confirmed` where both agree (else `held`). This is the automated
  confirmation gate. (Run by the daily routine; can also be invoked on demand.)
- `admin mockup-review` — prints the per-product checkpoint + agent-verdict table.
- `admin mockup-override <id> approve|hold` — **human escape hatch** only; the
  default path is fully agent-driven.
- `admin mockup-publish` — `rebuild-site` using only `confirmed` products' `live{}`,
  then the normal commit / push / UAT.
- **Daily routine `gelato-mockup-sync`** (existing scheduler cadence, ~07:xx):
  `mockup-sync` → `mockup-confirm` (the two agents) → email the report (confirmed /
  held-with-reasons / changed / error) → **auto-publish the confirmed** (a changed
  image always re-queues through the agents first, so a Gelato change can't ship
  unconfirmed). Because the agents are the confirmation, this whole loop needs **no
  human** — held items are the only thing surfaced for a person.

> The two agents are Claude subagents; the daily routine invokes them over the READY
> set (a scheduled Claude run or the Anthropic SDK). Their prompts/criteria live in
> `.claude/agents/gelato-mockup-reviewer.md` and `.claude/agents/gelato-sku-image-match.md`.

## Catalog lifecycle (feeds the pipeline)
A third agent, **`gelato-catalog-watcher`**, runs first in the daily routine and
keeps the *set of products* in lockstep with Gelato:
- **New** Gelato product/SKU → prepares a catalog entry (name, category, SKU,
  **price = Gelato cost → our margin floor**, print dims) and **queues its picture**
  into this mockup-sync pipeline (so the new product's photo is fetched →
  reviewed → matched → confirmed like any other). The SKU→UID mapping stays a human
  confirmation (standing rule: agents never auto-edit the mapping).
- **Discontinued** → flags the SKU unavailable (`catalog_state`) so it can't be sold
  or routed — the one state change safe to auto-apply (removes risk).
- **Changed cost/dims** → recommends the new price / print bound, warns on margin-floor.

Daily order: `gelato-catalog-watcher` (what products exist) → `mockup-sync` →
`mockup-confirm` (reviewer + match) → report → auto-publish confirmed. New products
thus arrive with the right SKU, price, and a confirmed picture; dropped products
disappear before anyone can buy an unfulfillable item.

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
- **Confirming agents (already created):** `.claude/agents/gelato-mockup-reviewer.md`
  and `.claude/agents/gelato-sku-image-match.md`. `mockup-confirm` dispatches both
  over each READY product and records their verdicts.
- `admin.py`: the `mockup-sync` / `mockup-confirm` / `mockup-review` /
  `mockup-override` / `mockup-publish` commands.
- `etsy/listing_preview.py`: `_mockBase()` reads `config/mockups.json` `live{}` (it
  already consumes the `brand/mockups/` manifest — same shape).
- `AUTOMATION_AGENTS.md` + scheduler: register the daily `gelato-mockup-sync` routine
  (sync → confirm via the two agents → report → auto-publish confirmed).

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
