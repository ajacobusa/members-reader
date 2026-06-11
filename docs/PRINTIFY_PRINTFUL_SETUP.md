# Printify & Printful Setup

QuoteForge fulfills orders through whichever vendor each order's `vendor`
column names — `gelato` (default), `printify`, or `printful`. The full
Etsy-style automation loop works for all three:

1. **Order intake** — the Etsy poller imports the paid order (vendor-agnostic).
2. **Fulfillment** — `fulfillment/router.py` routes the order to the vendor's
   API (`fulfillment/printify.py` / `fulfillment/printful.py`). The vendor's
   order id is stored on the order (in the `gelato_order_id` column, which
   holds the vendor order id for every vendor).
3. **Tracking sync** — the scheduled "QuoteForge Fulfillment Tracking" job
   polls the order's vendor every 6 hours, advances the order to
   shipped/delivered, and pushes the carrier + tracking number to the Etsy
   buyer (`createReceiptShipment`) — same as Gelato orders.

Everything is **key-gated and TEST_MODE-safe**: with no key set (or
`TEST_MODE=true`) the adapters return mock/manual results and never contact
the vendor, so orders are simply flagged for hand fulfillment.

## Printify

1. Log into [printify.com](https://printify.com)
2. My Profile → **Connections** → generate a **Personal Access Token**
3. Find your shop id: `GET https://api.printify.com/v1/shops.json`
   with header `Authorization: Bearer <token>`
4. Set in `.env`:

```
PRINTIFY_API_KEY=your_token
PRINTIFY_SHOP_ID=your_shop_id
```

Endpoints used:

| Call | Purpose |
|------|---------|
| `POST /v1/shops/{shop_id}/orders.json` | create the print order |
| `GET /v1/shops/{shop_id}/orders/{id}.json` | status + tracking |
| `GET /v1/shops.json` | auth verification (api-check) |

## Printful

1. Log into [printful.com](https://printful.com)
2. Settings → Stores → **API** → create a private token
3. Set in `.env`:

```
PRINTFUL_API_KEY=your_token
```

Endpoints used:

| Call | Purpose |
|------|---------|
| `POST /orders` | create the print order |
| `GET /orders/{id}` | status + tracking |
| `GET /orders?limit=1` | auth verification (api-check) |

## Verify

```bash
python -m quoteforge.admin verify-keys   # live auth check for all vendors
python -m quoteforge.admin preflight     # shows which keys are configured
python -m quoteforge.admin track-orders  # one tracking sync pass (all vendors)
```

`verify-keys` prints `[ -- ]` (not a failure) for any vendor whose key isn't
set — both vendors are optional until you route products to them.

## Routing an order to Printify/Printful

Set the order's `vendor` field (`printify` or `printful`) before the pipeline's
fulfillment stage — e.g. when the product line is fulfilled by that vendor.
Printify orders also need `line_items`; Printful orders need `variant_id`
(see each adapter's `create_order`). Orders missing these are returned as
`manual` and flagged for the operator, never dropped.
