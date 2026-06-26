"""Wave accounting GraphQL API client (https://gql.waveapps.com/graphql/public).

Key-gated + TEST_MODE-safe, exactly like the Gelato / Etsy integrations: nothing
touches the network without a real WAVE_API_TOKEN. Used to (a) verify the token and
discover the business + chart-of-accounts IDs, and (b) push a per-order Etsy payout
as a Wave money transaction.

Auth: Authorization: Bearer <full-access token>. A personal full-access token needs
no Wave Pro subscription. Amounts are plain decimals; the anchor is a Cash/Bank/
Credit-card account (DEPOSIT = money in, WITHDRAWAL = money out) and line items
categorize it (INCREASE = debit for asset/expense, credit for income/liability).
"""
from __future__ import annotations

ENDPOINT = "https://gql.waveapps.com/graphql/public"

_Q_BUSINESSES = """
query { businesses(page: 1, pageSize: 50) { edges { node {
  id name currency { code } } } } }
"""

_Q_ACCOUNTS = """
query($bid: ID!) { business(id: $bid) { accounts(page: 1, pageSize: 200) {
  edges { node { id name type { name value } subtype { name value } } } } } }
"""

_M_CREATE_TXN = """
mutation($input: MoneyTransactionCreateInput!) {
  moneyTransactionCreate(input: $input) {
    didSucceed
    inputErrors { code message path }
    transaction { id }
  }
}
"""


def _post(query: str, variables: dict | None = None) -> dict | None:
    """POST a GraphQL request to Wave. Returns the parsed JSON `data`, or None on any
    problem / when not configured. Never raises."""
    from quoteforge.config import TEST_MODE, WAVE_API_TOKEN
    if TEST_MODE or not WAVE_API_TOKEN:
        return None
    try:
        import requests
        resp = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {WAVE_API_TOKEN}",
                     "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
            timeout=30)
        if resp.status_code != 200:
            return None
        body = resp.json()
        if body.get("errors"):
            return {"_errors": body["errors"]}
        return body.get("data")
    except Exception:  # noqa: BLE001
        return None


def list_businesses() -> list[dict]:
    """[{id, name, currency}] for the token's businesses (empty if unconfigured)."""
    data = _post(_Q_BUSINESSES)
    if not data or "_errors" in data:
        return []
    edges = (((data.get("businesses") or {}).get("edges")) or [])
    return [{"id": e["node"]["id"], "name": e["node"]["name"],
             "currency": (e["node"].get("currency") or {}).get("code", "")}
            for e in edges if e.get("node")]


def list_accounts(business_id: str = "") -> list[dict]:
    """[{id, name, type, subtype}] - the chart of accounts to map income/fees/bank."""
    from quoteforge.config import WAVE_BUSINESS_ID
    bid = business_id or WAVE_BUSINESS_ID
    if not bid:
        return []
    data = _post(_Q_ACCOUNTS, {"bid": bid})
    if not data or "_errors" in data:
        return []
    edges = ((((data.get("business") or {}).get("accounts")) or {}).get("edges")) or []
    out = []
    for e in edges:
        n = e.get("node") or {}
        out.append({"id": n.get("id"), "name": n.get("name"),
                    "type": (n.get("type") or {}).get("value", ""),
                    "subtype": (n.get("subtype") or {}).get("value", "")})
    return out


def create_money_transaction(business_id: str, external_id: str, date: str,
                             description: str, anchor: dict,
                             line_items: list[dict]) -> dict:
    """Create one Wave money transaction. `anchor` = {accountId, amount, direction};
    each line item = {accountId, amount, balance}. Returns
    {ok, id, errors}. externalId makes the push idempotent (re-running is a no-op on
    Wave's side for the same id). Never raises."""
    inp = {"businessId": business_id, "externalId": external_id, "date": date,
           "description": description, "anchor": anchor, "lineItems": line_items}
    data = _post(_M_CREATE_TXN, {"input": inp})
    if not data:
        return {"ok": False, "id": "", "errors": ["not configured / no response"]}
    if "_errors" in data:
        return {"ok": False, "id": "",
                "errors": [e.get("message", "graphql error") for e in data["_errors"]]}
    res = data.get("moneyTransactionCreate") or {}
    if res.get("didSucceed"):
        return {"ok": True, "id": (res.get("transaction") or {}).get("id", ""),
                "errors": []}
    return {"ok": False, "id": "",
            "errors": [f"{e.get('code')}: {e.get('message')}"
                       for e in (res.get("inputErrors") or [])] or ["create failed"]}
