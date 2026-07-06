# Etsy Integration — Go-Live Runbook

Every step below is a real, deployed `admin` command. Nothing here fabricates a key, a UID,
or a token. The only inputs that are yours: the Etsy app key, the one-time browser OAuth
approval, and the go-live flips. Everything is a **safe no-op until `TEST_MODE=false`** — you
can run any command now to see status without touching production.

Run commands as `python -m quoteforge.admin <command>`.

---

## Phase 1 — Register + connect (one-time)

1. **Register an Etsy app** → https://www.etsy.com/developers → create app → copy the
   **keystring**. Register your redirect URI on the app.

2. **Set the Etsy env vars** (in `.env` / your secret manager — never hardcode):
   ```bash
   ETSY_API_KEY=<your keystring>
   ETSY_OAUTH_REDIRECT_URI=<must match your Etsy app exactly>
   ETSY_SHOP_ID=<your shop id>
   ETSY_WEBHOOK_SECRET=<any strong secret>
   # optional (defaults shown):
   ETSY_OAUTH_SCOPES="transactions_r listings_r listings_w email_r"
   ```

3. **Authorize your shop (OAuth 2.0 + PKCE):**
   ```bash
   admin etsy-connect status                     # what's set (booleans only, no secrets)
   admin etsy-connect start                       # prints the auth URL -> open + approve
   admin etsy-connect finish <CODE> <STATE>        # from the redirect's ?code & ?state
   ```
   Tokens are stored 0600 and NEVER printed/logged; auto-refresh is wired (the poller
   renews the access token without re-auth). Guard rails: PKCE (S256) + state/CSRF; a stray
   auth code is useless without this process's verifier.

---

## Phase 2 — Verify the connection

```bash
admin etsy-connect status                         # access/refresh tokens present?
admin verify-keys                                 # LIVE probe: Anthropic + Gelato + Etsy
```
`verify-keys` runs a real 1-row authenticated Etsy receipts call — PASS/FAIL/skip, no secrets.

---

## Phase 3 — Products + real images (so listings show the genuine product photo)

```bash
admin gelato-live doctor                          # checklist: EXACTLY what's missing + fix
admin gelato-resolve dry-run                       # auto-discover real Gelato productUids
admin gelato-uid list                              # review the drafted matches
admin gelato-uid verify <SKU>                      # check a UID against the Gelato API
admin gelato-uid approve <SKU>                     # admin approves it for go-live
admin gelato-readiness export                      # feed approved UIDs to the runtime map
```

Then get the real product photo. **Fastest path (recommended):** create ONE product in the
Gelato dashboard (or via Gelato's Etsy connector), then:
```bash
admin real-images pull                             # pull the real previewUrl, re-host, map
```
No template ID or API create-call needed. (Programmatic alternative:
`admin gelato-live create-product <TEMPLATE_ID> <TITLE>` — needs a template built in the
Gelato dashboard first; run `admin gelato-live doctor` to see if it's ready.)

The customer then sees their live design composited **in-browser** on that real photo — the
storefront swaps its generated tile for the genuine product image automatically.

---

## Phase 4 — Go-live gate

```bash
admin preflight                                   # HARD go-live gate (keys + mappings)
admin deploy-status                                # readiness checklist
```
Then flip the live switches (only after preflight passes):
```bash
TEST_MODE=false
# fulfillment mode - pick one:
GELATO_FULFILLMENT_MODE=native        # Gelato pulls the paid order from Etsy, prints, ships
#                     =quoteforge      # QuoteForge routes each order to Gelato (more control)
```

---

## Phase 5 — Orders flow (automatic, once live)

```bash
admin poll-etsy                                    # pulls paid Etsy receipts -> creates orders
```
Runs automatically on the scheduled `poll-etsy` job. The pipeline:

**Etsy paid receipt → `poll-etsy` → `create_order` → proof/lock gates → router (idempotent,
no double-charge) → Gelato print + ship → tracking synced back to Etsy → delivery/claims.**

---

## Ongoing / anytime (no-op until live)

```bash
admin gelato-readiness status                      # the 3 go-live gates
admin daily-uat                                    # automated self-test (runs daily 06:35)
admin validate-images                              # automated image validation status
admin gelato-live doctor                           # re-check first-live-product prerequisites
```

---

## Guard rails already enforced (daily infra-check, alerts on regression)

- **No double charge** — router dedups on the persisted vendor order id; the proof-resume
  path uses the same idempotent router; the calibration test order has a DB unique backstop.
- **Never order a placeholder** — a `GEL-*` UID is refused at order time and at write time.
- **UID approval lifecycle** — an auto-resolved UID must be admin-approved before it can go
  live; the resolver only drafts.
- **Apparel print calibration** — apparel is held until an owner (or capped, auto-reverting
  vision-QA) calibration; unverified apparel can't auto-print.
- **Customer approval ≠ auto-approval** — a customer's personalized order always needs their
  own affirmative authorization; the automated catalog-image validation can never approve it.
- **OAuth secrets** — tokens stored 0600, never printed/logged; PKCE + state/CSRF.

---

## What's yours vs automated

**Yours (irreducible):** register the Etsy app, click the browser OAuth approve, provide the
Gelato key, create one product (dashboard) + one physical test print, and flip the live
switches. **Automated:** UID discovery, image pull, validation, calibration, order routing,
tracking, self-tests, and exception-only alerts.
