# Make.com Automation Workflow — QuoteForge

## Overview
Make.com (formerly Integromat) connects Etsy orders to QuoteForge automatically.
Cost: ~$9/mo (much cheaper than Zapier).

## Complete Scenario Flow

```
[Etsy: Watch Orders] 
    → [Router]
        → [HTTP: POST to QuoteForge webhook]
        → [Airtable: Create record]
    → [Filter: Has personalization?]
        → [HTTP: Extract personalization fields]
        → [HTTP: POST to /order endpoint]
```

## Step-by-Step Setup

### Step 1: Start QuoteForge webhook server
```bash
# In Command Prompt:
python -m quoteforge.automation.webhook_server

# For public access (Zapier/Make):
ngrok http 5050
# Copy the https://xxx.ngrok.io URL
```

### Step 2: Create Make.com scenario

1. Log into make.com → Create a new scenario
2. Add module: **Etsy → Watch Orders** (new orders trigger)
3. Add module: **HTTP → Make a Request**
   - URL: `https://YOUR-NGROK-URL/order`
   - Method: POST
   - Body type: Raw (JSON)
   - Content type: `application/json`

### Step 3: Map Etsy personalization to JSON

```json
{
  "order_id": "{{order.id}}",
  "customer_name": "{{order.buyer_name}}",
  "recipient_name": "{{order.personalization.recipient_name}}",
  "relationship": "{{order.personalization.relationship}}",
  "occasion": "{{order.personalization.occasion}}",
  "scenery": "{{order.personalization.scenery}}",
  "tone": "{{order.personalization.tone}}",
  "memory": "{{order.personalization.special_memory}}",
  "output_style": "Personal Letter",
  "customer_email": "{{order.buyer_email}}",
  "total": "{{order.grandtotal}}"
}
```

> **Map the order total** (`total`) so reconciliation uses the *real* sale price
> per order instead of an estimate. The webhook accepts `total`, `sale_price`,
> `price`, `order_total`, or `grandtotal` and parses values like `$34.99`.

### Step 4: Add Airtable sync (optional)

Add module: **Airtable → Create a Record**
- Base: QuoteForge
- Table: Orders
- Map the same fields

### Step 5: Test

1. Place a test order on your Etsy shop
2. Check Make.com → Scenario History for success
3. Check `Desktop/QuoteForge-Output/Orders/` for generated text file
4. Check `Desktop/QuoteForge-Output/webhook_log.json` for log entry

## Production Tips

- Set scenario to run every 15 minutes (not real-time unless on higher plan)
- Add error handling: email yourself if webhook fails
- Add a filter: only process orders with personalization fields filled in
- Monitor Make.com operations — each scenario run uses ~3-5 operations

## Cost Comparison

| Tool | Cost | Operations/mo |
|---|---|---|
| Make.com Starter | $9/mo | 10,000 |
| Zapier Starter | $19.99/mo | 750 |
| Make.com Core | $16/mo | 10,000 |

**Make.com is ~50% cheaper than Zapier for this use case.**
