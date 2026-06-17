---
name: quoteforge-launch-qa
description: >-
  End-to-end QA, launch-readiness validation, and safe deployment for the
  QuoteForge print-on-demand storefront (code in quoteforge/, tests in
  quoteforge_tests/, generated storefront docs/index.html). Use this WHENEVER the
  work touches QuoteForge / the print-on-demand / Etsy-style shop and involves:
  validating the order workflow before launch, a go/no-go decision, auditing for
  the critical order-lifecycle risks, fixing a bug in the order/claims/tracking/
  fulfilment/financial code, changing customer-facing storefront copy or the
  frame/size/approval UX, or deploying any storefront change. Trigger even when
  the user only says things like "verify before launch", "is it ready to ship",
  "run the QA", "review end to end", "optimize the storefront", "make the picker
  more visual", "deploy this", or "give me the UAT link" — if it's QuoteForge,
  prefer this skill. It encodes the 21 order-lifecycle scope items, the 14
  critical risks, the fix-with-regression-test discipline, the hard
  customer-facing constraints (never expose supplier names or the marketplace
  name to customers), the branch→merge→backup→verify→UAT deploy loop, and the
  Go/No-Go report format.
---

# QuoteForge launch QA & safe deployment

QuoteForge is a made-to-order, personalized wall-art shop. Real money and real
prints are at stake, so the bar is: **no order is silently lost, no customer is
shown a supplier/marketplace name, nothing auto-refunds, and every fix ships with
a regression test and a green full suite.** This skill is the disciplined loop for
getting there and keeping it there.

## Orientation (read this first, it saves you grep time)

- **Product code:** `quoteforge/` — `etsy/` (listings, pricing, financials,
  resolution/policy, the storefront generator `listing_preview.py`),
  `fulfillment/` (`router.py`, `claim_service.py`, `claim_workflow.py`,
  `gelato_returns.py`, `tracking_api.py`), `automation/` (`pipeline_orchestrator.py`,
  `fulfillment_tracker.py`, `order_monitor.py`, `autopilot.py`, `webhook_server.py`,
  `gelato_api.py`, `full_backup.py`), `db/database.py`, `config.py`, `preflight.py`,
  `admin.py` (the ops CLI).
- **Tests:** `quoteforge_tests/` (~1160 tests, full run ≈ 8 min). `pyproject.toml`
  sets `testpaths = ["quoteforge_tests"]`.
- **Storefront:** `docs/index.html` is GENERATED from
  `quoteforge/etsy/listing_preview.py`. Never hand-edit `docs/index.html` as the
  source of truth — edit `listing_preview.py`, then regenerate with
  `python -m quoteforge.admin rebuild-site`. (Patching `docs/index.html` directly
  is fine only for a one-off check; the next rebuild overwrites it.)
- **UAT (always give this after a storefront change):**
  `https://ajacobusa.github.io/members-reader/` — gate password `Jesus`. GitHub
  Pages serves from `main`, so the UAT page only reflects work once it's merged to
  `main`.

## Commands you will lean on

```bash
# Full suite (the gate). ~8 min. Run in the background and wait for the result.
python -m pytest -q --no-header -p no:cacheprovider

# Targeted run while iterating
python -m pytest -q quoteforge_tests/test_<area>.py

# Profile what's slow (root-causing compute cost)
python -m pytest -q -p no:cacheprovider --durations=30

# Storefront regenerate + go-live gates
python -m quoteforge.admin rebuild-site        # regenerate docs/index.html
python -m quoteforge.admin verify-keys         # live auth test (Anthropic+Gelato)
python -m quoteforge.admin preflight           # hard go-live gate
python -m quoteforge.admin deploy-status       # readiness checklist
python -m quoteforge.admin gelato-sync         # placeholder-UID guard

# Backups (run after every merge to main)
python -m quoteforge.admin backup-all          # DB snapshot + commit + push + bundle
python -m quoteforge.admin verify-backup       # health check (no write); exit!=0 if stale
```

Long commands (the full suite, `backup-all`) should be run in the background and
awaited, not polled in a sleep loop.

## Grounding — do not hallucinate (verify before you claim)

Most "bugs" introduced during development here are hallucinations: a call to a
function/CLI/config key that doesn't exist, an assertion on a string the page
never actually renders, or a "tests pass" claim for a run that never happened.
Ground every reference in the real code — recall is not evidence:

- **Before you call or assert on a symbol, confirm it exists.** Grep/read for the
  function, method, attribute, CLI command (`admin.COMMANDS`), config constant
  (`config.py`), test name, status string, or column before using it. If you
  can't point to its definition, don't write it.
- **Cite file:line for claims about code.** "X is handled in `router.py:27`" must
  be a line you actually read, not a guess.
- **Audit findings get adversarially verified.** When auditing, read the code
  that proves the finding; don't infer behavior from a function name. A passing
  suite does not prove a path is wired — confirm reachability.
- **Editing the `listing_preview.py` page f-string is the top hallucination
  trap.** It is brace-escaped (`{{ }}` literal, `${{...}}` JS interpolation). A
  wrong brace or a phrase split across a `'+'` concatenation produces WRONG output
  silently (no Python error). After any storefront edit: `rebuild-site`, then
  `grep` the regenerated `docs/index.html` for the exact literal you intended and
  confirm count > 0. Don't trust that it rendered — check.
- **Never claim green without the output.** Run the suite (or the targeted file),
  then quote the real numbers ("1163 passed, 0 failed"). Never invent counts,
  durations, or "should pass". `verify-backup` must print `RESULT: HEALTHY` before
  you say backups are healthy.
- **Run the source-integrity guard after edits.** `test_source_integrity.py`
  byte-compiles every module (catches f-string/syntax breakage) and imports the
  core modules (catches dangling references). It is the fast net before the full
  suite; if it fails, you referenced something that isn't there.
- **When unsure, say so and check** rather than filling the gap with a plausible
  guess. A wrong-but-confident reference costs far more than a quick grep.

## The 21 scope items → where they live

Validate each against real code + a passing test. Many already have dedicated
tests (e.g. `test_routing_idempotency`, `test_delivery_integrity`,
`test_claim_window`, `test_margin_floor`). A green suite is necessary but NOT
sufficient — also confirm the behavior is actually wired end to end.

1. Custom order created — `webhook_server.process_webhook_payload` →
   `pipeline_orchestrator.create_order`.
2. Image upload + personalization stored — `pipeline_orchestrator` photo gate;
   storefront `checkUpload` / editor.
3. Final preview reviewed — storefront proof modal (`showFinalProof`).
4. Policy checkbox accepted — `_confirmChecklistHTML` (3 gating checkboxes).
5. Approve & Submit — affirmative authorization (see Constraints below).
6. Order locks after submission — `db/database.update_order` `LOCKED_FIELDS`
   guard keyed on `proof_approved` (raises `OrderLockedError`; `allow_locked`
   admin override).
7. Etsy-style order record + idempotency — `create_order`,
   `get_order_by_etsy_id`.
8. Routes to fulfilment supplier (idempotent) — `fulfillment/router.route_order`
   stores `vendor_order_id`; both the auto pipeline AND the customer-proof
   `resume_after_proof_approval` path must go through `route_order`.
9. Supplier order ID stored / missing-id detection — `order_monitor`.
10. Tracking number + carrier + ETA captured — `fulfillment_tracker`.
11. Status progression shipped→in transit→out for delivery→delivered —
    `tracking_api` mapping (out_for_delivery normalizes to in_transit; safe).
12. Delivery confirmed ONLY on carrier "delivered" — strict equality in
    `fulfillment_tracker._carrier_confirm` + Gelato exact match.
13. Review request not sent early — `etsy/delight_loop.delight_due` (bare
    `shipped` is NOT review-eligible; only delivered/manual-confirmed).
14. Claim page works — `webhook_server` `/service-request` →
    `claim_service.intake_claim`.
15. 7-day claim window enforced — `claim_service.validate_claim_request`:
    ≤7d normal; 8–30d held for ADMIN review (not auto-denied); >30d denied;
    `admin_override` is the only bypass.
16. Damage/defect/lost/wrong-item → manual review — `claim_service` →
    `supplier_review` (human queue).
17. Customer-approved spelling/sizing/design/photo issues denied/flagged —
    `etsy/resolution.py` customer-fault categories; never auto-refunded.
18. No automatic cancel/refund/return after submission — `autopilot` hard rule +
    a zero-dollar cap (AUTOPILOT_MAX_AUTO_REFUND defaults to 0); `_execute` has no money-out path.
19. Admin manual-review queue — `enqueue_approval` / `get_pending_approvals` /
    `admin approvals`.
20. Financial/margin/shipping-variance/status reports accurate — `etsy/financials`,
    `analytics/financial_reports`, `etsy/margin_guard`, `etsy/shipping_audit`,
    `etsy/reports`.
21. Deploy/env/migrations/secrets/logs/alerts/rollback — `preflight`,
    `config`, `db/database._migrate`, `admin._alert`, `full_backup`, `render.yaml`,
    `GO_LIVE_GUIDE.md`, `RESTORE.md`.

## The 14 critical risks (the audit checklist)

For each, find the guard, confirm it's reachable, and confirm a test pins it:

1. Order editable after approval → `LOCKED_FIELDS` guard.
2. Duplicate supplier submission → `route_order` idempotency (check BOTH the
   auto path and `resume_after_proof_approval`; a back-door direct
   `create_gelato_order` is the classic miss).
3. Missing supplier order ID → `order_monitor`.
4. Tracking missing/stale → `fulfillment_tracker` detectors + alert.
5. In-transit incorrectly marked delivered → strict "delivered"-only.
6. Review request before delivery → `delight_loop`.
7. Refund/return/cancel allowed automatically → `autopilot` hard rule + a zero-dollar cap (AUTOPILOT_MAX_AUTO_REFUND defaults to 0).
8. Claim accepted after 7 days without admin override → window tiers.
9. Missing evidence accepted for damage claim → `auto_replacement_block_reason`
   reuses `gelato_returns.build_claim_package().ready_to_file` (one evidence
   table, one window — don't let it drift).
10. Customer-approved mistake refunded → customer-fault denials.
11. Margin below floor → `margin_guard` + an order-time check in `order_monitor`
    (guard `sale_price is not None and gelato_cost:` so a zero-priced sale at real cost is
    still caught).
12. Shipping variance not detected → `shipping_audit`.
13. Failed deploy with no rollback → `GO_LIVE_GUIDE.md` rollback section +
    `verify-backup`.
14. Missing logs / silent failures → route owner alerts through `admin._alert`
    (logs on skip/raise) rather than `except: pass`; mark failed fulfilment
    `status="error"` and skip follow-up so the scheduled healthcheck alerts.

Two recurring "silent break" patterns worth grepping for every audit: a status
written by one module that NO consumer reads (orphan), and the same logical state
spelled two ways across modules (e.g. `canceled` vs `cancelled`). Either strands
orders silently.

## Fix discipline (non-negotiable, this is what makes it safe)

For every issue found, in order:

1. **Root cause** — read the code; name why it happens, not just the symptom.
2. **Severity** — Critical / High / Medium / Low.
3. **Fix the implementation** — minimal, behavior-preserving where possible; match
   surrounding style.
4. **Add an automated regression test** — name it after the risk and add a
   `# REGRESSION:` comment so the intent survives. A fix without a test will
   regress.
5. **Re-run the full suite** — `pytest` over all of `quoteforge_tests/`.
6. **Confirm no new failures** — quote the real count (e.g. "1163 passed, 0
   failed"). Never claim green without the output in front of you.

Prefer finding gaps with several focused read-only audit passes (clusters:
order/lock, tracking/delivery, claims/window, financial, deploy/observability,
storefront copy) and adversarially verifying each finding before fixing — the
real bugs hide in the less-traveled paths (e.g. the customer-proof resume path,
the webhook status map), which a passing suite won't surface.

## Hard customer-facing constraints (treat as launch blockers)

These come straight from the project rules and have bitten us repeatedly:

- **Never expose a supplier name to customers.** `Gelato`, `Printify`, `Printful`
  must NOT appear in any customer surface — that includes JS comments and JS
  identifiers in `docs/index.html` (view-source counts), the customer message
  templates (`etsy/customer_messages.py`), and the Ange bot (`ai/ange.py`). Use
  "the print partner". Fix the SOURCE in `listing_preview.py`, not just the
  generated file, or `rebuild-site` re-introduces the leak.
- **Never show the marketplace name "Etsy" in rendered customer copy.** (Internal
  docstrings/logs are fine.)
- **Policy language must match implemented behavior:** made to order; the order is
  final once confirmed at checkout; no returns/refunds/remakes for change of mind
  or for the wording/spelling/design/sizing/photo the customer approved; still
  covered for damaged/defective/wrong-item/non-delivery reported with a photo
  within 7 days. Don't overpromise ("we'll remake anything").
- **The final approval step is an affirmative authorization**, not a passive
  acknowledgement: "I approve this print exactly as shown and authorize it to
  proceed to production." This is the consent record the made-to-order policy
  rests on, gated behind the 3 checkboxes.
- Guard all of the above with tests (see `test_customer_copy_no_leak.py`,
  `test_ux_editor.py`). When you touch copy, also scan the SOURCE modules, not
  just the page.

If a `listing_preview.py` edit lives inside the big page f-string, remember it is
brace-escaped: literal JS braces are `{{ }}` and JS template interpolation is
`${{ ... }}`. A phrase you assert on must sit inside a single JS string literal,
or a `'+'` concatenation will split it in the rendered HTML.

## Safe-deploy loop (every change rides this)

Work happens on `main` only via this loop. Commit/push only when the user asks;
never skip hooks or force-push without being told.

1. **Branch** off `main` (never commit straight to the default branch):
   `git checkout -b <type>/<short-topic>`.
2. **Implement + test** per the fix discipline; regenerate `docs/index.html` with
   `rebuild-site` if the storefront changed.
3. **Full suite green** — quote the count.
4. **Commit** with a clear message; end the body with the Co-Authored-By line the
   environment requires.
5. **Push** the branch; open a PR with `gh pr create` (link PRs as full URLs).
6. **Merge to main** when the user approves: `git checkout main` →
   `git merge --no-ff <branch> -m "..."` → `git push origin main`. (Merging the
   default branch is the user's call — confirm first.)
7. **Refresh backups:** `python -m quoteforge.admin backup-all` then
   `python -m quoteforge.admin verify-backup` (expect `RESULT: HEALTHY`).
8. **Give the UAT link** (with the gate password) for any storefront change, and
   note it only reflects the work once merged to `main`.

To revert a merged change cleanly: `git revert -m 1 <merge-sha>`, then
`rebuild-site`, re-run the relevant tests, push, and refresh the backup.

## Go / No-Go report (use this structure)

```markdown
# QA Report — <scope> (<date>)

## Tests executed / results
- Full suite: <N> passed, <M> failed (<duration>)
- Regression tests added: <count>
- Smoke (preflight / 7-stage pipeline / margins gate): <pass/fail>

## Issues found & fixed
| # | Issue | Severity | Root cause | Fix | Regression test |

## Remaining risks
- <each item, severity, why it's non-blocking or what's needed>

## Acceptance criteria
- [ ] 100% of critical & high-risk tests pass
- [ ] Full automated suite passes
- [ ] E2E smoke + deployment validation pass
- [ ] Alerts & logs working; rollback verified
- [ ] No known production-blocking risks

## Go / No-Go
🟢 GO / 🔴 NO-GO — <one-line rationale + any operator gate, e.g. set live
ETSY_API_KEY before flipping TEST_MODE=false>
```

## Deploy keys (when the question is "what do we need to go live")

Source of truth: `.env.production.example` (tiered) + `preflight.REQUIRED_LIVE_KEYS`
(the hard gate: `ANTHROPIC_API_KEY`, `GELATO_API_KEY`, `ETSY_API_KEY`,
`ETSY_WEBHOOK_SECRET`). Functionally also required for the full flow: Etsy OAuth
(`ETSY_OAUTH_TOKEN`/`ETSY_REFRESH_TOKEN`/`ETSY_SHOP_ID`), `GELATO_WEBHOOK_SECRET`,
print-file hosting (Google Drive pair OR public-dir pair), `ASK_ANGE_API_URL`,
`TRACKING_API_KEY`, Gmail SMTP (`GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD`/
`REPORT_RECIPIENT`), `OUTPUT_DIR`. Also replace placeholder Gelato product UIDs
(the `gelato-sync` guard fails loudly otherwise) before flipping
`TEST_MODE=false`. On Render, share these via one env-var group across the web +
cron services; note Render disks are per-service (SQLite state isn't shared across
crons) — the self-hosted path shares one machine/DB and avoids that.

## Working notes

- Prefer dedicated read tools and the admin CLI over ad-hoc shell where one fits.
- The suite is slow if AI/network calls leak into TEST_MODE — gate
  `client.messages.create` sites on `TEST_MODE` (like `quotes/generator.py`), not
  just on API-key presence. That alone cut the suite ~31%.
- Taste-dependent UI (visual frame swatches, "popular" badges): show a small
  mockup and get direction first — a previous heavy image-tile picker was reverted
  as "not what expected". Keep the familiar layout and add a light cue (e.g. a
  color-swatch dot on the existing pills). Never fabricate social proof
  pre-launch — an honest, owner-curated "Editor's pick" beats a fake "bestseller".
