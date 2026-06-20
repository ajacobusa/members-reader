# Retire the email-proof approval round — on-screen approval is final

Date: 2026-06-19
Branch: `feat/how-it-works-redesign`
Owner decision: retire the emailed/messaged proof-approval round everywhere
(copy **and** the fulfillment gate), in favour of the on-screen editor flow.

## Problem

The storefront promises customers an **emailed proof you reply to before
printing** ("we email a FREE digital proof — reply right away and we fix it
before printing"). That contradicts the real, owner-confirmed flow: the customer
designs live in the on-screen editor, and **approving at submit is the final,
binding sign-off** (made-to-order). A PDF copy is saved under the customer ID and
optionally emailed **after** approval as a record.

Two proof models exist in the code:

- **Model A (keep) — on-screen, direct channel.** `confirm_design()` →
  `_intake_order()` → `create_order(channel="direct")`. The customer approves on
  screen; no email round.
- **Model B (retire) — emailed/messaged round.** `pipeline_orchestrator` Stage 5
  calls `automation/customer_proof.py:prepare_customer_proof()` which parks the
  order in `awaiting_customer_approval` and **blocks printing** until
  `record_customer_approval()` → `resume_after_proof_approval()`. Wired for
  marketplace/webhook orders (no live editor).

### Grounding (verified)

- The marketplace channel is **not operational**: `TEST_MODE=True`,
  `ETSY_API_KEY`/`ETSY_SHOP_ID`/`ETSY_OAUTH_TOKEN` unset, **no order DB exists**.
  Model B is dormant — no live order depends on it.
- **Pre-existing gap:** `_intake_order` (design_confirm.py:110-121) does **not**
  set `proof_approved` / `proof_approved_at`. So on-screen approval is not
  recorded in data — meaning direct orders today would be flagged by
  `order_monitor` ("production without approval"), would not engage the
  `LOCKED_FIELDS` lock, and would have **no evidence to deny a customer-fault
  dispute** (`etsy/resolution.py` needs `proof_approved_at`).
- DB already has the columns: `proof_sent`, `proof_approved`,
  `proof_approved_at`, `proof_file_hash` (db/database.py:76-78, 424).

## Design

Make on-screen approval **real in the data**, remove the customer email-proof
round, and keep a print-safety fail-safe so nothing ever auto-prints unapproved.

### Invariant after this change
> No order reaches the print vendor unless `proof_approved=1` is recorded.
> Direct (on-screen) orders record it at confirmation; any order without it
> **holds for owner review** — it is never auto-printed and never triggers a
> customer proof email.

### Part 1 — Copy (low-risk, reversible)
Rewrite every customer-facing surface to the on-screen-final model; drop "we
email a proof / reply to fix before printing". The email becomes a **PDF copy for
your records, sent after you approve**. Surfaces:

- `etsy/listing_preview.py`: FAQ (265-269), trust badge (2423), basket line
  (2564). (How-it-works + apparel-about + 3 marketing lines already done.)
- `ai/ange.py`: FAQ answers (46-53, 56-58, 85) — keep "ship" in the shipping
  answer and "make it right"/"team" in the returns answer (test_ange.py pins).
- `etsy/custom_copy.py` (27, 56), `etsy/listing_seo.py` (132),
  `etsy/subscription_product.py` (48, 87),
  `automation/customization_recovery.py` (59),
  `images/listing_pack.py` (159, 192), `marketing/pinterest.py` (138).
- `etsy/customer_messages.py`: "Order Received" ("send a proof within 24 hours")
  and "Proof Ready" templates — repurpose to a post-approval confirmation, or
  remove "Proof Ready" if it has no consumer (verify first).

### Part 2a — Record on-screen approval in data
`confirm_design()` / `_intake_order()` set `proof_approved=1`,
`proof_approved_at=<ISO now>`, and `proof_file_hash` (the proof→production parity
hash) for direct orders at creation. This makes the on-screen approval the audit
record disputes/locks/monitor depend on.

### Part 2b — Retire the email-proof gate + fail-safe
- `pipeline_orchestrator` Stage 5: remove the `CUSTOMER_PROOF_APPROVAL` customer
  branch that calls `prepare_customer_proof`. Replace the block with: if
  `proof_approved` is already set → continue to fulfillment; else → set
  `status="hold_owner_review"`, alert via `admin._alert`, and **stop** (no
  auto-print, no customer email).
- Retire `automation/customer_proof.py`'s buyer-facing message round
  (`prepare_customer_proof` customer message + `record_customer_approval`
  customer framing). Keep/representation of approval recording moves to the
  on-screen confirm + an owner-approval CLI.
- `admin.py`: reframe `show-proof` / `customer-approved` as **owner** review/
  approve (not "send to buyer / buyer replied"), or retire if redundant.
- Default config so the email gate cannot reactivate (document
  `CUSTOMER_PROOF_APPROVAL=false`).

### Keep (channel-agnostic safety — do NOT remove)
`proof_approved*` schema, `LOCKED_FIELDS` lock, `order_monitor`
production-without-approval check, `resolution.py` dispute evidence,
`validate_for_fulfillment` parity gate, `route_order` idempotency.

## Tests

- **Add (regression):**
  - `test_direct_order_records_onscreen_approval` — `confirm_design` with ship-to
    creates an order with `proof_approved=1` and a `proof_approved_at` timestamp.
  - `test_unapproved_order_holds_not_prints` — an order with `proof_approved=0`
    through the pipeline ends in `hold_owner_review` (or equivalent) and never
    calls `route_order`.
  - `test_no_email_proof_round_copy` — customer surfaces contain no "reply within
    24 hours" / "we email … proof … before printing" promise.
- **Refactor:** `test_customer_proof.py` to the owner-review/hold model (drop the
  "blocks printing until buyer replies" buyer-round assertions).
- **Keep passing:** `test_no_proof_promises_in_checkout_copy`, `test_ange.py`,
  `test_resolution.py`, `test_order_lock.py`, `test_order_monitor.py`,
  `test_apparel_fulfillment.py` (color lock), `test_customer_copy_no_leak.py`,
  `test_apparel_storefront.py`, `test_source_integrity.py`.
- Full suite green; quote the count.

## Risks
- **Silent auto-print** if Stage 5 removal is incomplete → mitigated by the
  fail-safe owner-hold default (unapproved = hold, never print).
- **Dispute evidence** for direct orders → mitigated by Part 2a recording
  `proof_approved_at` at confirmation.
- **Brace-escaped f-string** edits in `listing_preview.py` → rebuild-site +
  grep-verify each literal; run `test_source_integrity` before the full suite.
- **No supplier/marketplace name** in any customer copy — re-scan after edits.

## Out of scope
Re-enabling Etsy; changing the editor UX; the How-it-works visual redesign
(already shipped on this branch).
