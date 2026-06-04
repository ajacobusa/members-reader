# Airtable Setup Guide — QuoteForge

## Why Airtable?
- Central database visible to you and your VAs
- Filter orders by status (pending quote / pending design / shipped)
- Track revenue and analytics
- VA-friendly interface (no coding needed)

## Setup Steps

### 1. Create Airtable Base
1. Go to airtable.com → Create a new base
2. Name it: **QuoteForge**

### 2. Create "Orders" Table
Add these fields:
| Field | Type |
|---|---|
| Order ID | Single line text |
| Customer Name | Single line text |
| Recipient | Single line text |
| Occasion | Single line text |
| Relationship | Single line text |
| Status | Single select |
| Generated Quote | Long text |
| Artwork URL | URL |
| Tracking Number | Single line text |
| Gelato Order ID | Single line text |
| Created At | Date |

Status options: received, quote_generated, artwork_done, in_production, shipped, review_sent

### 3. Create "Products" Table
| Field | Type |
|---|---|
| Product ID | Single line text |
| Etsy Listing ID | Single line text |
| Category | Single line text |
| Gelato SKU | Single line text |
| Price USD | Currency |
| Active | Checkbox |

### 4. Get API Credentials
1. airtable.com → Account → Developer Hub
2. Personal Access Tokens → Create token
3. Scopes: `data.records:read`, `data.records:write`
4. Add your base to the token's access

### 5. Get Base ID
1. Open your QuoteForge base
2. URL: `https://airtable.com/appXXXXXXXXXXXXXX/...`
3. `appXXXXXXXXXXXXXX` is your Base ID

### 6. Configure QuoteForge
Add to `quoteforge/config.py`:
```python
AIRTABLE_API_KEY = "patXXXXXXXXXXXXXX.XXXXXXXX"
AIRTABLE_BASE_ID = "appXXXXXXXXXXXXXX"
```

### 7. Test Sync
```python
python -c "
from quoteforge.automation.airtable_client import sync_order_to_airtable
record_id = sync_order_to_airtable({
    'order_id': 'TEST-001',
    'customer_name': 'Test',
    'recipient_name': 'Emma',
    'occasion': 'Graduation',
    'status': 'received',
})
print('Airtable record:', record_id)
"
```
