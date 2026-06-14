# POC — Proof-of-Concept End-to-End Validation (TEST ONLY)

> ⚠️ **This is a TEST / UAT environment. It is never the primary site and never
> uses real customer data or real orders.** Everything here is for validating the
> full workflow before launch.

## What this is

A proof-of-concept harness that exercises the **real QuoteForge production code**
against an **isolated, seeded test database** with the vendor (Gelato), carrier
(AfterShip), and email systems **mocked offline**. It proves the system correctly
handles the full lifecycle — design → approval → order locking → supplier routing
→ tracking → delivery confirmation → review timing → claims → refund/reprint/
manual-review policy → reporting & profit — exactly like production, without
touching anything real.

It duplicates the deployed storefront as a clearly-labelled **POC site** so the UI
can be tested, and produces a **dashboard with a GO / NO-GO verdict**.

## Run it

```bash
python POC/run_poc.py
```

Outputs (regenerated each run, git-ignored):

- `POC/poc_dashboard.html` — metrics, the 15 scenarios, issues by severity, and
  the go/no-go verdict.
- `POC/poc_site/index.html` — the live storefront stamped as a TEST-ONLY POC site
  (warning banner + `POC site` title).
- `POC/poc_data/poc.db` — the throwaway seeded test database.

The command exits non-zero on a **NO-GO** verdict (so it can gate CI / a deploy).

Also available via the admin CLI: `python -m quoteforge.admin poc`.

## What it validates (maps to the testing plan)

| Agent | Validates |
|---|---|
| Customer | order locks after approval (snapshot stored), low-quality image held, abandonment recovery |
| Routing | approved order routes + **supplier order id stored**, **duplicate routing blocked**, bad address held (RTS prevented) |
| Tracking | in-transit/exception **never** confirm delivery, only carrier `Delivered` confirms, missing/stale tracking alerts |
| Policy | 7-day claim window enforced, evidence required, damaged/defect/wrong/lost qualify, approved-spelling-error & change-of-mind denied, late claim flagged, cancellation/refund after production → manual review, review not sent too early / suppressed on dispute |
| Financial | margin floor enforced, ledger revenue matches order data, refund/cancellation rates |
| Admin QA | production-before-approval flagged, compliance monitor, claim queue, repeat-customer detection |

## Go / No-Go

The POC is **GO** only when there are **zero critical and zero high** failures.
The dashboard lists every failure with a severity so it classifies straight into
the optimization backlog (Critical → must fix before launch; High → before real
traffic; Medium/Low → polish).

## Improvements this POC has already driven into production

- **Idempotent supplier routing** — `route_order()` now blocks duplicate
  submissions and self-stores the `vendor_order_id` (the POC's "duplicate routing
  is blocked" check surfaced the gap).
- **Documented deploy requirement** — carrier-confirmed delivery only runs when
  `TRACKING_API_KEY` is configured (the POC made this explicit).
