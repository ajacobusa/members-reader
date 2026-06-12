"""Etsy Open API v3 client — order intake (polling) + tracking push.

Removes the hard dependency on Make/Zapier for two flows:
  1. get_shop_receipts(): poll for new PAID orders to import into QuoteForge.
  2. create_receipt_shipment(): push carrier + tracking back onto the Etsy order
     so the buyer sees "Shipped" with tracking — the highest-value automation.

All calls are TEST_MODE-safe: with TEST_MODE on (or no credentials) they return
mock responses so the full flow is testable without contacting Etsy.

Auth: Etsy v3 uses OAuth2. Requests need the API key header AND a Bearer token.
"""
import requests

from quoteforge.config import (
    TEST_MODE, ETSY_API_KEY, ETSY_OAUTH_TOKEN, ETSY_SHOP_ID, ETSY_API_BASE,
)


def _headers() -> dict:
    """Build Etsy v3 auth headers (API key + OAuth bearer token)."""
    return {"x-api-key": ETSY_API_KEY,
            "Authorization": f"Bearer {ETSY_OAUTH_TOKEN}",
            "Content-Type": "application/json"}


def _credentials_ready() -> bool:
    """Check whether the Etsy API key, OAuth token, and shop ID are all set."""
    return bool(ETSY_API_KEY and ETSY_OAUTH_TOKEN and ETSY_SHOP_ID)


def get_shop_receipts(was_paid: bool = True, was_shipped: bool = False,
                      limit: int = 25) -> dict:
    """Fetch shop receipts (orders). Defaults to paid-but-not-yet-shipped."""
    if TEST_MODE or not _credentials_ready():
        return {"mock": True, "count": 0, "results": []}
    url = f"{ETSY_API_BASE}/application/shops/{ETSY_SHOP_ID}/receipts"
    params = {"was_paid": str(was_paid).lower(),
              "was_shipped": str(was_shipped).lower(), "limit": limit}
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_receipt_shipment(receipt_id: str, tracking_code: str,
                            carrier_name: str = "other",
                            send_bcc: bool = False) -> dict:
    """Push carrier + tracking onto an Etsy receipt (marks it shipped to the
    buyer). Mirrors Etsy's createReceiptShipment endpoint."""
    if not receipt_id or not tracking_code:
        return {"status": "skipped", "reason": "missing receipt_id/tracking"}
    if TEST_MODE or not _credentials_ready():
        return {"status": "mock_shipped", "receipt_id": receipt_id,
                "tracking_code": tracking_code, "carrier": carrier_name}
    url = (f"{ETSY_API_BASE}/application/shops/{ETSY_SHOP_ID}"
           f"/receipts/{receipt_id}/tracking")
    body = {"tracking_code": tracking_code, "carrier_name": carrier_name,
            "send_bcc": send_bcc}
    resp = requests.post(url, headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    return {"status": "shipped", **resp.json()}


def receipt_to_order_payload(receipt: dict) -> dict:
    """Map an Etsy receipt to the QuoteForge webhook payload shape.

    Personalization arrives in transaction 'variations'/'personalization'; we
    pull the common fields and leave the raw receipt id as etsy_order_id.
    """
    rid = str(receipt.get("receipt_id") or receipt.get("order_id") or "")
    name = receipt.get("name", "")
    # Personalization may live under transactions[].variations / personalization.
    personalization = {}
    for tx in receipt.get("transactions", []):
        for v in tx.get("variations", []):
            personalization[v.get("formatted_name", "").lower()] = \
                v.get("formatted_value", "")
        if tx.get("personalization"):
            personalization["personalization"] = tx["personalization"]
    return {
        "order_id": rid,
        "etsy_order_id": rid,
        "customer_name": name,
        "recipient_name": personalization.get("recipient name")
                          or personalization.get("name", ""),
        "occasion": personalization.get("occasion", ""),
        "relationship": personalization.get("relationship", ""),
        "memory": personalization.get("story")
                  or personalization.get("personalization", ""),
        "scenery": personalization.get("scenery", "Mountains"),
        "sale_price": (receipt.get("grandtotal", {}) or {}).get("amount"),
        "_raw_personalization": personalization,
    }
