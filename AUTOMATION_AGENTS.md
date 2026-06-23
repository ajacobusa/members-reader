# QuoteForge automation agents

Every recurring job runs hands-free on a schedule. Two deployment paths run the
same admin commands:

- **Render** — `cron` services in [`render.yaml`](render.yaml) (the hosted path).
- **In-process / Windows** — [`quoteforge/automation/scheduler.py`](quoteforge/automation/scheduler.py)
  (`SCHEDULED_JOBS`), installed with `python -m quoteforge.admin install-schedule`.

Run any agent on demand with `python -m quoteforge.admin <command>`.

---

## Schedule at a glance

| Agent | Command | Cadence | What it does |
|---|---|---|---|
| Morning briefing | `briefing email` | daily 07:20 | One consolidated ops read (orders, approvals, holds, health) |
| Ledger / reports | `report …` | daily/weekly/monthly | Sales + financial reports |
| Order tracking | `track-orders` | daily 07:20 | Pulls carrier tracking + status |
| Health check | `healthcheck email` | daily 07:20 | Alerts on DB/storage/job problems |
| **Gelato sync** | `gelato-sync` | daily 07:20 | Placeholder-UID guard; blocks go-live if mapping is incomplete |
| **Catalog sync** | `catalog-sync email` | daily 07:20 | Rebuilds the local product DB, validates images, emails the audit |
| **Gelato catalog review** | `gelato-review email` | daily (Render) + weekly Mon (scheduler) | Discontinued guard + new/removed product lines |
| **Product photos** | `product-photos email` | weekly Mon 08:00 | Downloads ready product images, files + publishes them |
| Site doctor | (site_doctor) | daily | Storefront self-QA |

The three **bold** Gelato agents are the product-mapping + imagery automation
documented below. None of them place an order or flip `TEST_MODE` — they are
read/report/prepare only.

---

## 1. Gelato sync (`gelato-sync`)

The loud guard. Scans the live family map for placeholder (`GEL-*`) or unmapped
UIDs and **blocks go-live** until every department maps to a real product. Emails an
alert if a placeholder is found. Source:
[`quoteforge/automation/gelato_sync.py`](quoteforge/automation/gelato_sync.py).

## 2. Gelato catalog review (`gelato-review`)

Keeps the mapping honest over time. Source:
[`quoteforge/automation/gelato_catalog_review.py`](quoteforge/automation/gelato_catalog_review.py).

- **Discontinued guard** — re-checks every mapped product UID for availability; a
  product Gelato dropped is flagged so it is remapped before it ships wrong.
- **New / removed lines** — diffs the catalog list + per-line product counts against
  the saved snapshot (`config/gelato_catalog_snapshot.json`).
- **Reports only** — never changes the mapping; emails the owner only when there is
  something to act on. A transient API failure never false-flags a live product.

## 2b. Wall-Art UID map (`wallart-automap`)

One-shot mapper (re-run when sizes change) that replaces the Wall-Art `GEL-*`
placeholder SKUs with REAL Gelato UIDs and writes them to the static map
(`GELATO_UID_MAP_FILE`, default `config/gelato_uid_map.json`). Source:
[`quoteforge/automation/gelato_wallart_map.py`](quoteforge/automation/gelato_wallart_map.py).

- Covers poster / canvas / framed / acrylic / metal across our 6 sizes, picking a
  portrait, standard-material default (silk poster, gallery-wrap canvas, black-wood
  frame, 4 mm acrylic, plain metal). Every UID is a real catalog UID — it only ever
  picks from what the API returns.
- **DRAFT for owner review** — confirm material/orientation per pick and place one
  test order per material before go-live. Never enables live ordering.
- **Known gaps to decide before go-live:**
  - Gelato acrylic & metal do **not** offer an 8×10 size (`GEL-ACRYLIC-8X10-ULT`,
    `GEL-METAL-8X10-ULT` stay unmapped) — change those two sizes or drop them.
  - `branded:phonecase` is **model-specific** on Gelato (iPhone-11, etc.); a single
    UID only serves one phone. Add a phone-model selector or drop phone cases.
  - Framed products default to a black-wood frame; the per-frame-colour composite
    SKUs need their own picks if you offer multiple frame colours.

Wall-Art tiles are **design-gallery driven** (generated occasion previews + the
`brand/wallart-hero.jpg` room shot), not per-product `tile-<id>.jpg` files — so Wall
Art is not part of the product-photo sheet below.

## 3. Product photos (`product-photos`) — the image pipeline

Automates "get the right photo onto the right product tile" so the owner never
hand-downloads or renames anything. Source:
[`quoteforge/automation/product_photo_agent.py`](quoteforge/automation/product_photo_agent.py).

### The product sheet

Columns (`config/product_photos.csv`, auto-generated with all 62 products):

```
product_id | product_name | gelato_product_url | mockup_image_url |
image_status | local_file_name | last_downloaded_date | notes
```

### What each run does, per row marked `Ready to Download`

1. Download `mockup_image_url` (with automatic retries).
2. Rename `tile-<product_id>.jpg`.
3. Save to **two** places:
   - live tile: `brand/tile-<product_id>.jpg` (what the storefront shows),
   - dated archive: `brand/product_photos/<YEAR>/<MONTH>/tile-<product_id>.jpg`.
4. Update the sheet: `image_status=Downloaded`, `local_file_name`,
   `last_downloaded_date`.
5. Rebuild the storefront so the new tile goes live.

### Status handling (exactly as specified)

| Condition | Result |
|---|---|
| Row not `Ready to Download` | skipped (untouched) |
| `mockup_image_url` empty | `image_status = Missing Image URL` |
| Download fails (after retries) | `image_status = Failed`, error written to `notes` |
| Tile already exists | `image_status = Already Exists` — **not overwritten** |
| `--overwrite` passed | existing tile IS replaced |
| Success | `image_status = Downloaded` + file + date |

Every action is logged; the owner is emailed on failures / missing URLs.

### Two ways to feed it

**A. Local CSV (default).** Edit `config/product_photos.csv`: paste each image URL
into `mockup_image_url`, set `image_status` to `Ready to Download`, then
`python -m quoteforge.admin product-photos`.

**B. Fully hands-free via Google Sheets (recommended).** The owner keeps the sheet
in Google and never touches a file:

1. Build a Google Sheet with the columns above (or copy `config/product_photos.csv`
   into one).
2. Paste image URLs into `mockup_image_url`; set `image_status` to
   `Ready to Download` on the rows to fetch.
3. **File → Share → Publish to web → CSV**, and copy the published link.
4. Set the env var `PRODUCT_PHOTOS_SHEET_URL` to that link (Render env group, or the
   local environment).
5. Done. The weekly agent reads the live sheet, downloads, files, rebuilds, and
   mirrors the results to the local sheet + emails a summary.

> Why CSV-publish and not the Sheets API: it needs no service-account credentials
> and keeps the data flow simple. The published link is read-only, so the agent
> mirrors download results to the local sheet and emails the log (the storefront
> updating is the live confirmation).

### Security

- The Gelato API key stays **backend-only** and is **not used** by this agent — it
  only fetches the owner-provided image URLs from the sheet.
- The agent **downloads** images (re-hosting them on our domain as
  `brand/tile-*.jpg`); it never hotlinks a supplier CDN, so no supplier URL ever
  appears in the page source (the customer-facing leak rule holds).

---

## Filenames reference

The exact `tile-<id>.jpg` name for every product is in
[`brand/PRODUCT_PHOTO_FILENAMES.md`](brand/PRODUCT_PHOTO_FILENAMES.md).

## Safety invariants (all agents)

- None place a Gelato order or change `TEST_MODE`.
- None modify the live family map automatically — they report and prepare.
- Network is injected in code, so the logic is unit-tested without live calls.
