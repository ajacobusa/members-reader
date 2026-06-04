# GO_LIVE_CHECKLIST.md

## QuoteForge Production Launch Checklist

> **The key rule:** Software works (165/165 tests passing), but **print quality
> must be physically verified before live automation.** No automated test can
> confirm color, text spacing, or packaging — only holding the printed piece can.
>
> **Re-run the automated checks anytime:** `python -m quoteforge.preflight`
> It verifies every ✅ software item below and prints pass/fail with evidence.
>
> Legend: ✅ verified by tests/preflight · ⚙️ your config step · ⬜ manual / physical

### Safest Launch Order (Anthropic + Gelato first, Etsy last)

```
1. Add to .env:   ANTHROPIC_API_KEY,  GELATO_API_KEY
2. Verify:        python -m quoteforge.admin verify-keys     (both [PASS])
3. Preview AI:    python -m quoteforge.admin sample-quote    (judge real quality)
4. Sample flow (KEEP TEST_MODE=true — Gelato stays manual):
      real AI quote → artwork → MANUAL Gelato sample → physical print approved
5. Only after print approved, add: ETSY_API_KEY, ETSY_SHOP_ID,
      BANNERBEAR_API_KEY, BANNERBEAR_TEMPLATE_UID, UNSPLASH_ACCESS_KEY
6. Finally:       TEST_MODE=false
```

Do NOT enable Etsy live fulfillment until the physical sample is approved.

### Current Status

- [x] ✅ Development Complete
- [x] ✅ Integration Testing Complete (165/165 tests)
- [x] ✅ High Availability & Recovery Hardened (NEW — see Phase 1.5)
- [ ] ⬜ Physical Print Verification Complete
- [ ] ⚙️ Production Credentials Configured
- [ ] ⚙️ TEST_MODE Disabled

---

# Phase 1: Software Verification

## Environment

- [ ] ⚙️ `.env` created (`cp .env.example .env`)
- [ ] ⚙️ All required API keys configured (preflight lists which are set)
- [x] ✅ Database migrations completed (auto-migrates on `init_db()`)
- [x] ✅ Streamlit monitor operational (`quoteforge/web_monitor.py`)
- [x] ✅ Webhook server operational (`quoteforge/automation/webhook_server.py`)

## Automated Testing

- [x] ✅ All unit tests passing (165/165)
- [x] ✅ All integration tests passing
- [x] ✅ End-to-end pipeline test passing (`test_full_pipeline_e2e.py`)
- [x] ✅ Webhook signature verification passing
- [x] ✅ Airtable sync verified (graceful skip when unconfigured)
- [x] ✅ Gelato test order verified (mock in TEST_MODE)

## TEST_MODE Verification

- [x] ✅ TEST_MODE=true confirmed (default)
- [x] ✅ Mock quote generation verified
- [x] ✅ Mock artwork generation verified (real 30KB placeholder PNG)
- [x] ✅ Mock Gelato fulfillment verified
- [x] ✅ Customer messages generated (5 lifecycle messages persisted)
- [x] ✅ Upsell workflow generated (canvas / framed / bundle)
- [x] ✅ Review workflow generated (scheduled +14 days)

---

# Phase 1.5: High Availability, Performance & Recovery  ⟵ **WAS MISSING**

## Concurrency & Performance

- [x] ✅ SQLite WAL mode + 30s busy_timeout (20-thread concurrent write test)
- [x] ✅ Atomic webhook log (lock + temp-file replace, 30-thread test)
- [x] ✅ Async webhook — `/order` returns HTTP 202, processes in background
- [x] ✅ Production WSGI server supported (waitress) ⚙️ run `pip install waitress`

## Idempotency (no duplicate charges)

- [x] ✅ Orders keyed by Etsy order ID (`get_order_by_etsy_id`)
- [x] ✅ Duplicate webhook returns HTTP 200 `duplicate` (sender stops retrying)
- [x] ✅ Webhook routes through full pipeline → lands in DB + monitor

## Resilience

- [x] ✅ Claude quote call retries transient errors (429/529/5xx/timeout)
- [x] ✅ Gelato order call retries with exponential backoff
- [x] ✅ Permanent errors (4xx) fail fast — no wasted retries

## Recovery

- [x] ✅ Online DB backup (`backup_database()`) + 14-day rotation
- [x] ✅ `POST /backup` endpoint for scheduled snapshots
- [ ] ⚙️ Scheduled daily backup configured (cron / Render Cron → `POST /backup`)
- [ ] ⬜ Restore drill performed once (copy a snapshot over `quoteforge.db`, restart)

## Monitoring

- [x] ✅ Deep `/health` endpoint (verifies DB, returns 503 if down)
- [ ] ⚙️ Uptime monitor pointed at `/health` (UptimeRobot / Render health check)
- [ ] ⚙️ Error alerting configured (notify on `status='error'` orders)

---

# Phase 2: Real API Verification

## Gelato

- [ ] ⚙️ GELATO_API_KEY added to `.env`
- [ ] ⚙️ Product catalog synchronized
- [ ] ⚙️ Product UID mappings verified (set `gelato_product_uid` per product)

## Etsy

- [ ] ⚙️ Etsy API credentials verified (ETSY_API_KEY, ETSY_SHOP_ID)
- [ ] ⚙️ Etsy webhook verified + ETSY_WEBHOOK_SECRET set (enables signature checks)
- [ ] ⚙️ Etsy listing personalization fields verified (copy from Order Processor tab)
- [ ] ⚙️ Make.com / Zapier scenario live and test-fired

## OpenAI / Claude

- [ ] ⚙️ Real quote generation tested (set ANTHROPIC_API_KEY, TEST_MODE still true)
- [ ] ⬜ Prompt quality reviewed
- [x] ✅ No copyrighted content (prompts enforce 100% original wording)
- [ ] ⚙️ API spend cap / budget alert set (Anthropic console)

## Canva / Bannerbear

- [ ] ⚙️ Production template verified (layers `quote_text`, `background_image`)
- [ ] ⚙️ Dynamic text insertion verified
- [ ] ⬜ Artwork export verified (real render, not the TEST_MODE placeholder)

---

# Phase 3: Artwork Quality Review  (manual — cannot automate)

## Layout

- [ ] ⬜ Text inside safe area (Gelato trims ~3mm bleed)
- [ ] ⬜ No clipping
- [ ] ⬜ No overflow
- [ ] ⬜ Proper margins

## Resolution

- [ ] ⬜ Exported at 300 DPI
- [ ] ⬜ Correct dimensions for product size
- [ ] ⬜ No pixelation

Recommended minimum sizes (matches `config.py` PRODUCTS):

| Size | Pixels @ 300 DPI |
|---|---|
| 8x10 | 2400 × 3000 |
| 11x14 | 3300 × 4200 |
| 16x20 | 4800 × 6000 |
| 18x24 | 5400 × 7200 |
| 24x36 | 7200 × 10800 |

## Typography

- [ ] ⬜ Font readable
- [ ] ⬜ Proper spacing
- [ ] ⬜ Line breaks reviewed
- [ ] ⬜ Long names tested (e.g. "Alexandria", hyphenated names)

---

# Phase 4: Physical Print Validation  (manual — the go-live gate)

## Sample Order

- [ ] ⬜ Place Etsy order to yourself
- [ ] ⬜ Generate real artwork
- [ ] ⬜ Submit real Gelato order
- [ ] ⬜ Receive physical print

## Print Inspection — Color

- [ ] ⬜ Colors match screen
- [ ] ⬜ No color shift
- [ ] ⬜ Contrast acceptable

## Print Inspection — Quality

- [ ] ⬜ Sharp text
- [ ] ⬜ No blur
- [ ] ⬜ No artifacts

## Print Inspection — Material

- [ ] ⬜ Poster quality acceptable
- [ ] ⬜ Frame quality acceptable
- [ ] ⬜ Canvas quality acceptable

## Print Inspection — Packaging

- [ ] ⬜ Arrived undamaged
- [ ] ⬜ Packaging acceptable
- [ ] ⬜ Customer experience acceptable

---

# Phase 5: Soft Launch

- [ ] ⬜ Launch first 10 listings
- [ ] ⬜ Monitor first 5 orders manually (Pipeline Monitor tab / Streamlit)
- [ ] ⬜ Review support workflow
- [ ] ⬜ Verify tracking numbers (`check_and_update_tracking` on a schedule)

---

# Phase 6: Production Launch

**ONLY AFTER ALL PREVIOUS ITEMS ARE COMPLETE**

- [ ] ⚙️ TEST_MODE=false (in `.env`)
- [ ] ⚙️ Real fulfillment enabled
- [ ] ⚙️ Production monitoring active (Streamlit monitor / `/health` uptime check)
- [ ] ⚙️ Backup database configured (scheduled `POST /backup`)
- [ ] ⬜ Daily order review process established
- [ ] ⬜ **Disaster rollback rehearsed:** set `TEST_MODE=true` to instantly halt
      live fulfillment if something goes wrong

## Production Approval

Run final preflight: `python -m quoteforge.preflight`

Launch Date: ___________

Approved By: ___________

Notes:

---

## What Changed in This Review

Tasks **added** that were missing from the original checklist:

1. **Entire Phase 1.5 (High Availability & Recovery)** — concurrency, idempotency,
   resilience, recovery, monitoring. None of this was tracked before.
2. **Make.com / Zapier scenario live + test-fired** (Phase 2).
3. **ETSY_WEBHOOK_SECRET** set for signature verification (Phase 2).
4. **API spend cap / budget alert** (Phase 2) — runaway API cost protection.
5. **Scheduled daily backup + restore drill** (Phase 1.5 recovery).
6. **Uptime monitor + error alerting** (Phase 1.5 monitoring).
7. **Disaster rollback rehearsal** — flip `TEST_MODE=true` to halt fulfillment (Phase 6).
8. **Final preflight run** before sign-off.
