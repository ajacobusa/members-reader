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
    """Build Etsy v3 auth headers (API key + the FRESHEST OAuth bearer token - the
    static env token expires hourly, so use the auto-refreshed one)."""
    from quoteforge.automation.etsy_auth import current_access_token
    return {"x-api-key": ETSY_API_KEY,
            "Authorization": f"Bearer {current_access_token()}",
            "Content-Type": "application/json"}


def _credentials_ready() -> bool:
    """Check whether the Etsy API key, shop id, and a usable token (the live access
    token OR a refresh token to mint one) are all set."""
    from quoteforge.automation.etsy_auth import (current_access_token,
                                                 current_refresh_token)
    return bool(ETSY_API_KEY and ETSY_SHOP_ID
                and (current_access_token() or current_refresh_token()))


def get_shop_receipts(was_paid: bool = True, was_shipped: bool = False,
                      limit: int = 25) -> dict:
    """Fetch shop receipts (orders). Defaults to paid-but-not-yet-shipped.
    Auto-refreshes the OAuth token on a 401 (expired ~hourly) and retries once."""
    if TEST_MODE or not _credentials_ready():
        return {"mock": True, "count": 0, "results": []}
    url = f"{ETSY_API_BASE}/application/shops/{ETSY_SHOP_ID}/receipts"
    params = {"was_paid": str(was_paid).lower(),
              "was_shipped": str(was_shipped).lower(), "limit": limit}

    def _do():
        """The receipts GET, run (and retried once on a 401) by with_refresh."""
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    from quoteforge.automation.etsy_auth import with_refresh
    return with_refresh(_do)


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

    def _do():
        """The tracking POST, run (and retried once on a 401) by with_refresh."""
        resp = requests.post(url, headers=_headers(), json=body, timeout=30)
        resp.raise_for_status()
        return {"status": "shipped", **resp.json()}
    from quoteforge.automation.etsy_auth import with_refresh
    return with_refresh(_do)


def _money(m: dict) -> float:
    """Convert an Etsy money object ({amount, divisor}) to a float, or 0.0."""
    try:
        return round(float(m.get("amount", 0)) / float(m.get("divisor", 100) or 100), 2)
    except (AttributeError, TypeError, ValueError):
        return 0.0


def receipt_to_order_payload(receipt: dict) -> dict:
    """Map an Etsy receipt to the QuoteForge webhook payload shape, including
    the REAL order total, shipping collected, sales tax collected, and ship-to
    destination (so reporting uses Etsy's actual figures, not estimates).

    Personalization arrives in transaction 'variations'/'personalization'; we
    pull the common fields and leave the raw receipt id as etsy_order_id.
    """
    rid = str(receipt.get("receipt_id") or receipt.get("order_id") or "")
    name = receipt.get("name", "")
    txns = receipt.get("transactions", []) or []

    def _person(tx: dict) -> dict:
        """Per-transaction personalization (variations + personalization note)."""
        p = {}
        for v in tx.get("variations", []):
            p[(v.get("formatted_name", "") or "").lower()] = v.get("formatted_value", "")
        if tx.get("personalization"):
            p["personalization"] = tx["personalization"]
        return p

    def _line(tx: dict) -> dict:
        """One purchased Etsy transaction -> one order line (its OWN personalization,
        size, quantity and PRE-TAX line price - so each item is fulfilled separately
        and priced from its own field, never the basket total)."""
        p = _person(tx)
        qty = int(tx.get("quantity", 1) or 1)
        unit = _money(tx.get("price") or {})
        line = {
            "recipient_name": p.get("recipient name") or p.get("name", "") or name,
            "occasion": p.get("occasion", ""),
            "relationship": p.get("relationship", ""),
            "memory": p.get("story") or p.get("personalization", ""),
            "scenery": p.get("scenery", "Mountains"),
            "product_size": p.get("size", "") or p.get("format", ""),
            "quantity": qty,
            "listing_title": tx.get("title", ""),
            "_raw_personalization": p,
        }
        if unit:
            line["sale_price"] = round(unit * qty, 2)
        return line

    # Order-level financials (the WHOLE receipt) - used for payout reconciliation.
    # Only customer + address propagate to lines (see _ORDER_LEVEL); totals do not.
    payload = {
        "order_id": rid,
        "etsy_order_id": rid,
        "customer_name": name,
        "sale_price": _money(receipt.get("grandtotal") or {}),
        "shipping_collected": _money(receipt.get("total_shipping_cost") or {}),
        "tax_collected": _money(receipt.get("total_tax_cost") or {})
                         + _money(receipt.get("total_vat_cost") or {}),
        "country": receipt.get("country_iso", ""),
        "state": receipt.get("state", ""),
    }
    if len(txns) > 1:
        # MULTI-ITEM: one line per transaction so EVERY purchased product is created
        # + fulfilled. The old code merged all transactions into one personalization
        # (last wins) and returned a single flat order at the full grand total, so
        # every item but the last was silently dropped.
        payload["items"] = [_line(tx) for tx in txns]
        first = payload["items"][0]
        payload["recipient_name"] = first["recipient_name"]
        payload["occasion"] = first["occasion"]
        payload["_raw_personalization"] = _person(txns[0]) if txns else {}
    else:
        # SINGLE-ITEM: unchanged flat shape (back-compat).
        p = _person(txns[0]) if txns else {}
        payload.update({
            "recipient_name": p.get("recipient name") or p.get("name", ""),
            "occasion": p.get("occasion", ""),
            "relationship": p.get("relationship", ""),
            "memory": p.get("story") or p.get("personalization", ""),
            "scenery": p.get("scenery", "Mountains"),
            "_raw_personalization": p,
        })
    return payload
