"""Automated Gelato catalog review agent.

Runs on a schedule (daily) to keep our product mapping honest:
  * DISCONTINUED guard - every mapped product UID is re-checked for availability;
    a UID Gelato has dropped is flagged so it can be remapped before it ships wrong.
  * NEW / REMOVED product lines - the catalog list and per-line product counts are
    compared to last run's snapshot, so new offerings (or retired ones) surface.

It only REPORTS/alerts - it never changes the live mapping or places an order. All
network access is injected so the logic is unit-tested without live calls.
"""
from __future__ import annotations


def relevant_catalogs() -> list[str]:
    """The Gelato catalogs our families map into."""
    from quoteforge.automation.gelato_automap import FAMILY_PLAN
    return sorted({c for c, _ in FAMILY_PLAN.values() if c})


def review_catalog(check_uid, list_catalogs, count_catalog,
                   family_map: dict, prev_snapshot: dict) -> dict:
    """Pure review logic (inject the three fetchers).

    - ``check_uid(uid) -> bool``  : is this product still available on Gelato?
    - ``list_catalogs() -> list`` : current catalogUids
    - ``count_catalog(cat) -> int``: number of products in a catalog (for additions)
    """
    prev_snapshot = prev_snapshot or {}
    discontinued = []
    for fam, uid in sorted(family_map.items()):
        try:
            ok = check_uid(uid)
        except Exception:  # noqa: BLE001 - a network blip must not false-flag
            ok = True
        if not ok:
            discontinued.append({"family": fam, "uid": uid})

    try:
        cur_cats = sorted(set(list_catalogs() or []))
    except Exception:  # noqa: BLE001
        cur_cats = sorted(prev_snapshot.get("catalogs", []))
    prev_cats = set(prev_snapshot.get("catalogs", []))
    new_catalogs = [c for c in cur_cats if c not in prev_cats] if prev_cats else []
    removed_catalogs = sorted(prev_cats - set(cur_cats)) if prev_cats else []

    prev_counts = prev_snapshot.get("counts", {})
    counts, count_changes = {}, {}
    for c in relevant_catalogs():
        try:
            n = count_catalog(c)
        except Exception:  # noqa: BLE001
            n = prev_counts.get(c)
        counts[c] = n
        old = prev_counts.get(c)
        if old is not None and n is not None and n != old:
            count_changes[c] = {"was": old, "now": n, "delta": n - old}

    return {
        "discontinued": discontinued,
        "new_catalogs": new_catalogs,
        "removed_catalogs": removed_catalogs,
        "count_changes": count_changes,
        "snapshot": {"catalogs": cur_cats, "counts": counts},
        "summary": {
            "discontinued": len(discontinued),
            "new_catalogs": len(new_catalogs),
            "removed_catalogs": len(removed_catalogs),
            "lines_changed": len(count_changes),
        },
    }


def format_review(res: dict) -> str:
    """Human-readable report for the console / owner email."""
    s = res["summary"]
    lines = ["GELATO CATALOG REVIEW", "=" * 40,
             f"Discontinued mapped products: {s['discontinued']}",
             f"New product lines: {s['new_catalogs']}   "
             f"Removed lines: {s['removed_catalogs']}   "
             f"Lines with count changes: {s['lines_changed']}", ""]
    if res["discontinued"]:
        lines.append("ACTION - these mapped products are no longer on Gelato; remap them:")
        for d in res["discontinued"]:
            lines.append(f"  - {d['family']}  ({d['uid'][:48]})")
        lines.append("")
    if res["new_catalogs"]:
        lines.append("NEW product lines available to add:")
        lines += [f"  + {c}" for c in res["new_catalogs"]]
        lines.append("")
    if res["removed_catalogs"]:
        lines.append("Product lines Gelato removed:")
        lines += [f"  - {c}" for c in res["removed_catalogs"]]
        lines.append("")
    if res["count_changes"]:
        lines.append("Within-line product additions/removals:")
        for c, ch in res["count_changes"].items():
            lines.append(f"  ~ {c}: {ch['was']} -> {ch['now']} ({ch['delta']:+d})")
    if not (res["discontinued"] or res["new_catalogs"]
            or res["removed_catalogs"] or res["count_changes"]):
        lines.append("No changes since the last review. Catalog is in sync.")
    return "\n".join(lines)


# ── live (network) fetchers ─────────────────────────────────────────
def gelato_check_uid(uid: str) -> bool:
    """Live: is this product UID still available on Gelato? (read-only GET)."""
    import requests
    from quoteforge.config import GELATO_API_KEY
    r = requests.get(f"https://product.gelatoapis.com/v3/products/{uid}",
                     headers={"X-API-KEY": GELATO_API_KEY}, timeout=20)
    return r.status_code == 200


def gelato_list_catalogs() -> list[str]:
    """Live: the current list of Gelato catalogUids (read-only GET)."""
    import requests
    from quoteforge.config import GELATO_API_KEY
    r = requests.get("https://product.gelatoapis.com/v3/catalogs",
                     headers={"X-API-KEY": GELATO_API_KEY}, timeout=25)
    return [c.get("catalogUid") for c in (r.json() or {}).get("data", [])
            if c.get("catalogUid")]


def gelato_count_catalog(catalog: str) -> int | None:
    """Live: total number of products in a Gelato catalog (the search 'hits')."""
    import requests
    from quoteforge.config import GELATO_API_KEY
    r = requests.post(
        f"https://product.gelatoapis.com/v3/catalogs/{catalog}/products:search",
        headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
        json={"limit": 1}, timeout=25)
    d = r.json() or {}
    return d.get("hits") if isinstance(d.get("hits"), int) else None
