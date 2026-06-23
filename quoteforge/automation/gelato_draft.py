"""Gelato DRAFT-order preview tool.

A Gelato *draft* order is saved on Gelato but is NEVER sent to production and is
NEVER charged - it exists only so the owner can review Gelato's own production proof
(the real product render) before go-live. This module can ONLY ever create draft
orders: the order type is a hardcoded constant and is asserted before every send, so
there is no code path that places a production order or spends money.
"""
from __future__ import annotations

DRAFT_ORDER_TYPE = "draft"          # hardcoded - never parameterised
GELATO_ORDERS_V4 = "https://order.gelatoapis.com/v4/orders"
DASHBOARD_ORDER = "https://dashboard.gelato.com/orders/"


def build_draft_payload(product_uid: str, design_url: str, *,
                        reference: str = "preview", quantity: int = 1,
                        currency: str = "USD", ship_to: dict | None = None) -> dict:
    """Build a DRAFT order payload. ``orderType`` is always ``draft`` - never live."""
    payload = {
        "orderType": DRAFT_ORDER_TYPE,
        "orderReferenceId": f"draft-{reference}",
        "customerReferenceId": f"draft-{reference}",
        "currency": currency,
        "items": [{
            "itemReferenceId": f"draft-{reference}-item-1",
            "productUid": product_uid,
            "files": [{"type": "default", "url": design_url}],
            "quantity": quantity,
        }],
    }
    if ship_to:
        payload["shippingAddress"] = ship_to
    return payload


def assert_draft(payload: dict) -> None:
    """Defense in depth: refuse to send anything that is not a draft order."""
    if payload.get("orderType") != DRAFT_ORDER_TYPE:
        raise ValueError("REFUSED: gelato_draft can only create DRAFT orders, "
                         f"got orderType={payload.get('orderType')!r}")


def create_draft_order(product_uid: str, design_url: str, *,
                       reference: str = "preview", quantity: int = 1,
                       ship_to: dict | None = None) -> dict:
    """Create ONE Gelato DRAFT order (never production, never charged). Returns the
    API JSON. Guarded: refuses to send if the payload is not a draft."""
    import requests
    from quoteforge.automation.gelato_api import _gelato_headers
    payload = build_draft_payload(product_uid, design_url, reference=reference,
                                  quantity=quantity, ship_to=ship_to)
    assert_draft(payload)                       # hard guard before any network call
    r = requests.post(GELATO_ORDERS_V4, headers=_gelato_headers(),
                      json=payload, timeout=45)
    r.raise_for_status()
    return r.json()


def delete_draft_order(gelato_order_id: str) -> bool:
    """Delete a draft order (cleanup after review). Returns True on success."""
    import requests
    from quoteforge.automation.gelato_api import _gelato_headers
    r = requests.delete(f"{GELATO_ORDERS_V4}/{gelato_order_id}",
                        headers=_gelato_headers(), timeout=30)
    return r.status_code in (200, 204)
