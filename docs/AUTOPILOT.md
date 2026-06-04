# Autopilot — autonomous decisions with a human safety gate

QuoteForge runs the business on autopilot. Bots make every routine decision
automatically and pull you in **only when it genuinely matters**.

## The rule

A decision auto-executes when **all** of these hold:

| Gate | Default |
|---|---|
| Classifier confidence ≥ threshold | `AUTOPILOT_CONFIDENCE_THRESHOLD=0.80` |
| No money leaves the business | `AUTOPILOT_MAX_AUTO_REFUND=0` |
| Risk is not `high` | — |
| Order value ≤ high-value cap | `AUTOPILOT_HIGH_VALUE_ORDER=150` |

Otherwise the decision is **staged in your approval queue** with its full
rationale — you just approve or reject.

## What the bots handle automatically

- **Damage / defect / poor quality / lost package** → files a Gelato replacement
  claim and drafts the customer reply (Gelato-covered, $0 out of your pocket).
- **Clear customer-fault denials** (changed mind, wrong personalization, approved
  then changed mind) → sends the polite, policy-based decline (backed by the
  proof-approval record).
- The whole order pipeline, mockups, scheduling, backups, health, margin checks.

## What always needs you (by design)

- **Refunds / spending money** beyond the cap (cancellations with a refund).
- **High-value orders** above the cap.
- **Ambiguous issues** the classifier isn't sure about.
- **Going live**: flipping `TEST_MODE`, physical sample sign-off, and the
  customer's own proof approval (that's the buyer's call, never a bot's).

## Commands

```bash
# Let the bot decide an issue (auto-acts or escalates):
python -m quoteforge.admin autopilot "my framed print arrived cracked" QF-123

# Your decision queue — usually empty:
python -m quoteforge.admin approvals
python -m quoteforge.admin approvals approve 7
python -m quoteforge.admin approvals reject 7
```

Incoming issues can also hit the signed **`POST /issue`** webhook (Make.com / a
contact form), and they route through the same engine. Pending approvals also
appear in the daily maintenance email so nothing waits unseen.

## Tuning

Everything is env-configurable. To let the bot auto-approve small refunds, raise
`AUTOPILOT_MAX_AUTO_REFUND` (e.g. `15`). To require a human for everything, set
`AUTOPILOT_ENABLED=false`. To classify fuzzy free-text with Claude, set
`AUTOPILOT_USE_LLM=true` (falls back to keywords if no key).
