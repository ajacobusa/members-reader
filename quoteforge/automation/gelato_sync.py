"""Gelato catalog sync — keep prices + availability current automatically.

Periodically queries Gelato for each product/frame SKU we sell and writes the
result to catalog_state (availability + latest cost). Because variation pricing
re-derives from current cost on every build, this means:

  * a Gelato PRICE CHANGE  -> our retail price auto-recomputes to hold 60%,
  * a DISCONTINUED product -> that variation/frame auto-disappears from listings.

Real-time note: Gelato's price/availability changes are pulled on a schedule
(default daily; can run more often). If Gelato exposes catalog webhooks for your
account, point them at the webhook server to make this event-driven instead.

Mapping: our internal SKUs (e.g. GEL-FRAME-OAK-PRM) must be mapped to real
Gelato product UIDs in GELATO_UID_MAP (config/env) for live lookups. Unmapped
SKUs are left untouched (assumed available) so nothing breaks before mapping.
In TEST_MODE or without a key, this is a safe no-op.
"""
from __future__ import annotations

import json
import os


def _uid_map() -> dict:
    """our_sku -> gelato_product_uid. From GELATO_UID_MAP env (JSON) if present."""
    raw = os.getenv("GELATO_UID_MAP", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def _all_skus() -> list[str]:
    """Every Gelato SKU we sell (catalog products + frames + apparel), sorted."""
    from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
    from quoteforge.etsy.frames import FRAMES
    from quoteforge.etsy.apparel_catalog import apparel_skus
    skus = {p.gelato_sku for p in GELATO_CATALOG}
    skus |= {f.gelato_sku for f in FRAMES}
    skus |= set(apparel_skus())          # apparel availability/cost syncs too
    return sorted(skus)


def _fetch_one(uid: str) -> dict:
    """Live availability + cost for one Gelato product UID.
    Returns {'available': bool, 'cost': float|None}."""
    import requests
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    headers = {"X-API-KEY": GELATO_API_KEY}
    try:
        info = requests.get(
            f"https://product.gelatoapis.com/v3/products/{uid}",
            headers=headers, timeout=15)
        if info.status_code == 404:
            return {"available": False, "cost": None}   # discontinued / unknown
        if info.status_code != 200:
            return {}                                    # transient: leave as-is
        prices = requests.get(
            f"https://product.gelatoapis.com/v3/products/{uid}/prices",
            headers=headers, timeout=15)
        cost = None
        if prices.status_code == 200:
            rows = prices.json()
            vals = [r.get("price") for r in rows if isinstance(r, dict) and r.get("price")]
            cost = round(min(vals), 2) if vals else None
        return {"available": True, "cost": cost}
    except Exception:  # noqa: BLE001 — network blip: don't change state
        return {}


def sync_catalog() -> dict:
    """Refresh catalog_state from Gelato. Returns a summary dict."""
    from quoteforge.config import TEST_MODE
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    from quoteforge.etsy.catalog_state import load_state, save_state

    # Go-live guard: every product must carry a REAL Gelato UID. A leftover
    # placeholder means orders silently fail to route, so surface it on every
    # sync (the admin command escalates this to a loud alert when live).
    from quoteforge.etsy.gelato_catalog import verify_catalog_mappings
    from quoteforge.etsy.apparel_catalog import verify_apparel_mappings
    m = verify_catalog_mappings()
    am = verify_apparel_mappings()
    # Surface BOTH print and apparel placeholders in the one loud banner so a
    # leftover apparel GEL-* UID can't silently ship (apparel placeholders are
    # SKU strings; shape them like the print entries format_sync_text expects).
    ph = {"placeholder_uids": m["placeholder_count"] + am["placeholder_count"],
          "placeholders": m["placeholders"] + [
              {"product_id": s, "size": "apparel", "current_sku": s}
              for s in am["placeholders"]]}

    skus = _all_skus()
    if TEST_MODE or not GELATO_API_KEY:
        return {"mock": True, "checked": len(skus), "updated": 0,
                "discontinued": 0, "message": "TEST_MODE/no key - no live sync",
                **ph}

    uid_map = _uid_map()
    state = load_state().get("skus", {})
    updated = discontinued = unmapped = 0
    for sku in skus:
        uid = uid_map.get(sku)
        if not uid:
            unmapped += 1
            continue
        res = _fetch_one(uid)
        if not res:
            continue
        prev = state.get(sku, {})
        if prev != res:
            updated += 1
        if res.get("available") is False:
            discontinued += 1
        state[sku] = res
    save_state(state)
    return {"mock": False, "checked": len(skus), "updated": updated,
            "discontinued": discontinued, "unmapped": unmapped,
            "message": f"{updated} changed, {discontinued} discontinued, "
                       f"{unmapped} unmapped (add to GELATO_UID_MAP)", **ph}


def format_sync_text(r: dict) -> str:
    """Render the catalog sync summary as a short plain-text block (with a loud
    banner when any product is still on a placeholder Gelato UID)."""
    lines = []
    if r.get("placeholder_uids"):
        n = r["placeholder_uids"]
        lines += ["!" * 56,
                  f"  CRITICAL: {n} product(s) still on PLACEHOLDER Gelato UIDs -",
                  "  orders for these WILL FAIL TO ROUTE. Replace with real UIDs",
                  "  from your Gelato account in quoteforge/etsy/gelato_catalog.py.",
                  "!" * 56]
        for p in r.get("placeholders", [])[:8]:
            lines.append(f"    - {p['product_id']} ({p['size']}): {p['current_sku']}")
        if n > 8:
            lines.append(f"    ... and {n - 8} more")
        lines.append("")
    lines += ["Gelato catalog sync", "-" * 32,
              f"  Checked     : {r.get('checked', 0)} SKUs",
              f"  Updated     : {r.get('updated', 0)}",
              f"  Discontinued: {r.get('discontinued', 0)}",
              f"  {r.get('message', '')}"]
    return "\n".join(lines)
