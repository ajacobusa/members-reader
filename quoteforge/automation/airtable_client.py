"""Airtable sync client.

Syncs QuoteForge order data to an Airtable base for team visibility.
Configure in config.py: AIRTABLE_API_KEY, AIRTABLE_BASE_ID.
"""
import os
import requests
from typing import Optional

AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_ORDERS: str = os.getenv("AIRTABLE_TABLE_ORDERS", "Orders")
AIRTABLE_TABLE_PRODUCTS: str = os.getenv("AIRTABLE_TABLE_PRODUCTS", "Products")

BASE_URL = "https://api.airtable.com/v0"


def _headers() -> dict:
    if not AIRTABLE_API_KEY:
        raise ValueError("AIRTABLE_API_KEY not set. Add to config.py or environment.")
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"}


def _is_configured() -> bool:
    return bool(AIRTABLE_API_KEY and AIRTABLE_BASE_ID)


def sync_order_to_airtable(order: dict) -> Optional[str]:
    """Push/update an order record in Airtable. Returns Airtable record ID."""
    if not _is_configured():
        return None  # silently skip if not configured

    fields = {
        "Order ID": order.get("order_id", ""),
        "Customer Name": order.get("customer_name", ""),
        "Recipient": order.get("recipient_name", ""),
        "Occasion": order.get("occasion", ""),
        "Relationship": order.get("relationship", ""),
        "Status": order.get("status", "received"),
        "Generated Quote": (order.get("generated_quote") or "")[:99000],
        "Artwork URL": order.get("artwork_url", ""),
        "Tracking Number": order.get("tracking_number", ""),
        "Gelato Order ID": order.get("gelato_order_id", ""),
        "Created At": order.get("created_at", ""),
    }

    url = f"{BASE_URL}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ORDERS}"
    resp = requests.post(url, headers=_headers(), json={"fields": fields}, timeout=10)
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    return None


def update_airtable_order(airtable_record_id: str, fields: dict) -> bool:
    """Update specific fields on an existing Airtable record."""
    if not _is_configured() or not airtable_record_id:
        return False
    url = f"{BASE_URL}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ORDERS}/{airtable_record_id}"
    resp = requests.patch(url, headers=_headers(), json={"fields": fields}, timeout=10)
    return resp.status_code == 200


def get_airtable_setup_instructions() -> str:
    return """
AIRTABLE SETUP — QuoteForge Database
======================================

1. Go to airtable.com → Create a new Base named "QuoteForge"

2. Create table: "Orders" with these fields:
   - Order ID (Single line text)
   - Customer Name (Single line text)
   - Recipient (Single line text)
   - Occasion (Single line text)
   - Relationship (Single line text)
   - Status (Single select: received, quote_generated, artwork_done, in_production, shipped, review_sent)
   - Generated Quote (Long text)
   - Artwork URL (URL)
   - Tracking Number (Single line text)
   - Gelato Order ID (Single line text)
   - Created At (Date)

3. Create table: "Products" with these fields:
   - Product ID (Single line text)
   - Etsy Listing ID (Single line text)
   - Category (Single line text)
   - Gelato SKU (Single line text)
   - Price USD (Currency)
   - Active (Checkbox)

4. Get your API key:
   airtable.com/account → Developer Hub → Personal Access Tokens → Create token
   Scopes: data.records:read, data.records:write

5. Get your Base ID:
   Open your base → Help → API documentation → copy "YOUR_BASE_ID"

6. Set in quoteforge/config.py:
   AIRTABLE_API_KEY = "your_pat_token"
   AIRTABLE_BASE_ID = "appXXXXXXXXXXXXXX"
"""
