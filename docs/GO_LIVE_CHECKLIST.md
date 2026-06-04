# GO_LIVE_CHECKLIST.md

## QuoteForge Production Launch Checklist

> **The key rule:** Software works (137/137 tests passing), but **print quality
> must be physically verified before live automation.** No automated test can
> confirm color, text spacing, or packaging — only holding the printed piece can.
>
> Items marked ✅ are verified by the automated test suite. Items marked ⬜ are
> your manual actions (require real accounts / physical inspection).

### Current Status

- [x] ✅ Development Complete
- [x] ✅ Integration Testing Complete (137/137 tests)
- [ ] ⬜ Physical Print Verification Complete
- [ ] ⬜ Production Credentials Configured
- [ ] ⬜ TEST_MODE Disabled

---

# Phase 1: Software Verification

## Environment

- [ ] ⬜ `.env` created (`cp .env.example .env`)
- [ ] ⬜ All required API keys configured
- [x] ✅ Database migrations completed (auto-migrates on `init_db()`)
- [x] ✅ Streamlit monitor operational (`quoteforge/web_monitor.py`)
- [x] ✅ Webhook server operational (`quoteforge/automation/webhook_server.py`)

## Automated Testing

- [x] ✅ All unit tests passing
- [x] ✅ All integration tests passing
- [x] ✅ End-to-end pipeline test passing (`test_full_pipeline_e2e.py`, 11 tests)
- [x] ✅ Webhook signature verification passing (`test_zip_parity.py`)
- [x] ✅ Airtable sync verified (graceful skip when unconfigured)
- [x] ✅ Gelato test order verified (mock in TEST_MODE)

## TEST_MODE Verification

- [x] ✅ TEST_MODE=true confirmed (default)
- [x] ✅ Mock quote generation verified
- [x] ✅ Mock artwork generation verified (real 30KB placeholder PNG on disk)
- [x] ✅ Mock Gelato fulfillment verified (`TEST-GELATO-*` order ID)
- [x] ✅ Customer messages generated (5 lifecycle messages persisted)
- [x] ✅ Upsell workflow generated (canvas / framed / bundle)
- [x] ✅ Review workflow generated (scheduled +14 days)

---

# Phase 2: Real API Verification

## Gelato

- [ ] ⬜ GELATO_API_KEY added to `.env`
- [ ] ⬜ Product catalog synchronized
- [ ] ⬜ Product UID mappings verified (set `gelato_product_uid` per product)

## Etsy

- [ ] ⬜ Etsy API credentials verified (ETSY_API_KEY, ETSY_SHOP_ID)
- [ ] ⬜ Etsy webhook verified (set ETSY_WEBHOOK_SECRET for signature checks)
- [ ] ⬜ Etsy listing personalization fields verified (copy from Order Processor tab)

## OpenAI / Claude

- [ ] ⬜ Real quote generation tested (set ANTHROPIC_API_KEY, TEST_MODE still true)
- [ ] ⬜ Prompt quality reviewed
- [ ] ⬜ No copyrighted content generated (prompts already enforce originality)

## Canva / Bannerbear

- [ ] ⬜ Production template verified (layers named `quote_text`, `background_image`)
- [ ] ⬜ Dynamic text insertion verified
- [ ] ⬜ Artwork export verified (real render, not the TEST_MODE placeholder)

---

# Phase 3: Artwork Quality Review

## Layout

- [ ] ⬜ Text inside safe area (Gelato trims ~3mm bleed)
- [ ] ⬜ No clipping
- [ ] ⬜ No overflow
- [ ] ⬜ Proper margins

## Resolution

- [ ] ⬜ Exported at 300 DPI
- [ ] ⬜ Correct dimensions for product size
- [ ] ⬜ No pixelation

Recommended minimum sizes (matches `quoteforge/config.py` PRODUCTS):

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

# Phase 4: Physical Print Validation

## Sample Order

- [ ] ⬜ Place Etsy order to yourself
- [ ] ⬜ Generate real artwork
- [ ] ⬜ Submit real Gelato order
- [ ] ⬜ Receive physical print

## Print Inspection

### Color

- [ ] ⬜ Colors match screen
- [ ] ⬜ No color shift
- [ ] ⬜ Contrast acceptable

### Print Quality

- [ ] ⬜ Sharp text
- [ ] ⬜ No blur
- [ ] ⬜ No artifacts

### Material

- [ ] ⬜ Poster quality acceptable
- [ ] ⬜ Frame quality acceptable
- [ ] ⬜ Canvas quality acceptable

### Packaging

- [ ] ⬜ Arrived undamaged
- [ ] ⬜ Packaging acceptable
- [ ] ⬜ Customer experience acceptable

---

# Phase 5: Soft Launch

- [ ] ⬜ Launch first 10 listings
- [ ] ⬜ Monitor first 5 orders manually
- [ ] ⬜ Review support workflow
- [ ] ⬜ Verify tracking numbers

---

# Phase 6: Production Launch

**ONLY AFTER ALL PREVIOUS ITEMS ARE COMPLETE**

- [ ] ⬜ TEST_MODE=false (in `.env`)
- [ ] ⬜ Real fulfillment enabled
- [ ] ⬜ Production monitoring active (Streamlit monitor or Pipeline tab)
- [ ] ⬜ Backup database configured (`quoteforge.db` — copy on a schedule)
- [ ] ⬜ Daily order review process established

## Production Approval

Launch Date: ___________

Approved By: ___________

Notes:

---
