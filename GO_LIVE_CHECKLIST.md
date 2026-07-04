# Go-Live Readiness Checklist — flipping `TEST_MODE=false` safely

This is the **technical gate** for turning the shop from test mode to real money. It
complements `GO_LIVE_GUIDE.md` (which covers publishing on Etsy + hosting). Do these
in order. **Nothing here charges a card until Step 7** — the earlier steps only
configure and verify.

> Source of truth for every key: `.env.production.example` (tiered) and
> `quoteforge/preflight.py` (`REQUIRED_LIVE_KEYS`, the hard gate). Verify with
> `python -m quoteforge.admin verify-keys` / `preflight` / `deploy-status`.

---

## Step 0 — Where things live
- Copy `.env.production.example` → `.env` **on the production machine** and fill real
  values. Never commit a filled-in `.env` (it's git-ignored).
- Every command below is `python -m quoteforge.admin <command>`.

---

## Step 1 — The 5 hard-gate keys (orders won't route without them)
`preflight` **fails** until all of these are set (`preflight.REQUIRED_LIVE_KEYS`):

| Key | What it's for |
|---|---|
| `ANTHROPIC_API_KEY` | Quote + artwork generation |
| `GELATO_API_KEY` | Submitting the print order |
| `ETSY_API_KEY` | Order polling + tracking push |
| `ETSY_WEBHOOK_SECRET` | Verifies inbound Etsy order webhooks (rejects spoofed orders) |
| `GELATO_WEBHOOK_SECRET` | Verifies Gelato status/tracking callbacks — **without it the verifier fails CLOSED in live and rejects everything**, so it's a hard block. Set the *same* secret in Gelato's webhook settings and in `.env`. |

---

## Step 2 — Functional-required env (the full order flow needs these)
Not in the hard gate, but the end-to-end flow breaks without them:

- **Etsy OAuth:** `ETSY_OAUTH_TOKEN`, `ETSY_REFRESH_TOKEN`, `ETSY_SHOP_ID`
  (scope `listings_r`/`listings_w` + transactions). The token auto-refreshes once
  live (the publisher now uses `current_access_token()` + refresh-on-401), but you
  must seed the initial OAuth token + refresh token.
- **Print-file hosting** (Gelato must FETCH the customer's JPG) — set **either**:
  - Google Drive: `GOOGLE_DRIVE_FOLDER_ID` + `GOOGLE_SERVICE_ACCOUNT_FILE`, **or**
  - Public dir: `PUBLIC_FILE_DIR` + `PUBLIC_FILE_BASE_URL` (served over HTTPS).
- **Backend URL:** `ASK_ANGE_API_URL` (the running webhook server's `/ask`; the claim
  form + widgets derive from it).
- **Carrier tracking:** `TRACKING_API_KEY` (+ `TRACKING_API_PROVIDER`). Carrier-
  confirmed delivery only runs when this is set.
- **Owner email/alerts:** `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `REPORT_RECIPIENT`.
- **Storage:** `OUTPUT_DIR` — a persistent, writable, backed-up path.

---

## Step 3 — Replace EVERY placeholder Gelato product UID ⚠️ (the money-critical one)
A wrong or placeholder UID means **the wrong product gets printed and shipped**, or the
order can't route at all.

1. Replace every placeholder UID (e.g. `GEL-POSTER-8X10-STD`, `GEL-*`) in
   `quoteforge/etsy/gelato_catalog.py` with the **real** UID from your Gelato account.
2. Draft-builders to speed this up (they never auto-commit a mapping):
   - `admin gelato-automap` → apparel/mug/calendar/branded family map
     (optionally point `GELATO_PRODUCT_FAMILY_FILE` at the result).
   - `admin wallart-automap` → wall-art `our_sku → UID` map
     (optionally point `GELATO_UID_MAP_FILE` at the result).
3. **Guard:** `admin gelato-sync` **fails loudly and emails you** if any placeholder UID
   remains in live mode. It must pass clean before go-live.

---

## Step 4 — Prevent double-printing / double-charging ⚠️
Exactly ONE system may submit orders to Gelato, or every order double-prints **and**
double-charges your card.

- Keep `GELATO_FULFILLMENT_MODE=quoteforge` (the default — QuoteForge generates the
  personalized artwork and submits it).
- In Gelato's dashboard, **DISCONNECT Gelato's native Etsy integration.** If it stays
  connected it would ignore the personalized art (print the static listing image) *and*
  submit a duplicate order.

---

## Step 5 — Set the webhook secrets on BOTH dashboards
- Etsy: set `ETSY_WEBHOOK_SECRET` in `.env` and the matching secret in your Etsy app.
- Gelato: set `GELATO_WEBHOOK_SECRET` in `.env` and the *same* value in Gelato's webhook
  settings. (Mismatch → the verifier rejects real callbacks and tracking never updates.)

---

## Step 6 — Verify GREEN before flipping the switch
Run these and confirm each is clean:

```
python -m quoteforge.admin verify-keys     # live auth test (Anthropic + Gelato)
python -m quoteforge.admin gelato-sync     # placeholder-UID guard passes
python -m quoteforge.admin preflight       # hard go-live gate (no FAILs)
python -m quoteforge.admin deploy-status   # readiness checklist
python -m quoteforge.admin healthcheck     # DB/storage/backups/jobs/uptime/token OK
```

Also register the daily jobs with `admin install-schedule` (then confirm in Windows
Task Scheduler) so backups, healthcheck, infra-check, and the sync jobs actually run.
`healthcheck` includes a **Scheduled Jobs** check that flags any missing/disabled job.

---

## Step 7 — Flip to live, then place ONE real test order
1. Set `TEST_MODE=false` in `.env`. (This is the go-live decision — yours alone.)
2. Restart the app / services so the new env is picked up.
3. Place **one real Etsy order to yourself** for a personalized item and confirm the
   full path: order webhook received → artwork generated → print file hosted → routed
   to Gelato (correct product) → tracking flows back → delivered → review request only
   after carrier-confirmed delivery.
4. Watch the owner alert emails for any `error`-status order or health warning.

---

## If something goes wrong
- **Code/deploy bad:** roll back per `GO_LIVE_GUIDE.md` → "Rolling back a bad deploy"
  (`git revert <sha>`, then `rebuild-site`).
- **Data corruption:** `RESTORE.md` (`restore-all`) — it snapshots the current DB first,
  so the rollback is itself reversible.
- Re-confirm with `admin healthcheck` and the `/health` endpoint (expect HTTP 200).

---

### Still-open build blocker (not an owner step)
`#167 faithful apparel print render` — the apparel design must print exactly as the
customer previewed/approved. Until that's shipped, apparel is held behind the safety
gate; wall-art / mugs / other flat products are unaffected.
