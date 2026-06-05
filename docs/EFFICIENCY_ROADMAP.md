# Efficiency Roadmap — expert-review response

A technical review recommended improving the 3 manual/fragile points and adding
new tech. Here's what was **implemented now** vs. **deferred until scale** (and
why), so nothing is lost.

## Implemented now (code, tested)

| Recommendation | Status | Where |
|---|---|---|
| Etsy API polling for order intake (drop Make/Zapier) | ✅ Done | `automation/etsy_api.py`, `automation/etsy_poller.py`, scheduled job "Etsy Order Poll" (every 10 min), `admin poll-etsy` |
| Tracking auto-update back to Etsy (`createReceiptShipment`) | ✅ Done | `etsy_api.create_receipt_shipment`, fired from the `/gelato` callback |
| **Artwork preflight checker** (size/DPI/mode/aspect, block on fail) | ✅ Done | `images/preflight.py`, pipeline Stage 5.5, `admin preflight-art` |
| AI issue classifier for support | ✅ Done earlier | `automation/autopilot.py` (keyword + optional Claude) |
| Keep proof approval semi-manual | ✅ By design | `customer_proof.py` — bot never auto-approves the buyer's proof |

The single most-valuable upgrade (Gelato callback → QuoteForge → Etsy tracking)
is live: when Gelato reports tracking, the buyer sees "Shipped" on Etsy
automatically — no Make step.

> Both Etsy paths are TEST_MODE-safe: they no-op until real Etsy OAuth
> credentials (`ETSY_OAUTH_TOKEN`, `ETSY_SHOP_ID`) are set, so they're inert
> until you go live.

## Deferred until orders increase (intentionally)

These are **deployment/scaling** choices, not launch blockers. Adopting them
before there's volume is premature complexity (YAGNI). Revisit at the noted
trigger.

| Upgrade | Trigger to adopt | Notes |
|---|---|---|
| **Postgres** instead of SQLite | ~sustained >1 order/min or multi-host | SQLite (WAL) is plenty for a single-node shop; the DB layer is small and isolated, so the swap is contained. |
| **Celery / RQ / Cloud Tasks** | when webhook background threads aren't enough | Today the webhook ACKs 202 and processes in a daemon thread; fine at launch volume. |
| **Sentry / Logtail** | as soon as you host publicly | Drop-in: wrap the webhook server + admin entrypoints. Worth doing early — low effort, high signal. |
| **Render / Railway / Fly.io** hosting | when you stop running it on your PC | The webhook server is a standard Flask/waitress app; deploys as-is. |
| **Secure customer approval page** | post-launch | Replaces the paste-into-Etsy proof step with a link; manual approval is safer for emotional custom gifts at launch. |

## Recommended order (unchanged from the review)

1. Keep current system for launch.
2. Add real Anthropic + Gelato keys; run a sample print.
3. Turn on Etsy API polling + tracking push (set the OAuth env vars). ✅ built
4. Preflight checker guards every real print. ✅ built
5. Move to Postgres only when volume demands it.
