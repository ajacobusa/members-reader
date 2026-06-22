"""Nightly Gelato catalog synchronization — local product DB + audit + validation.

A fuller companion to `gelato_sync` (which only refreshes per-SKU price/
availability). This builds and maintains a LOCAL PRODUCT DATABASE so the website
reads a fast local snapshot instead of hitting Gelato during browsing, and runs a
daily feedback loop:

    build local catalog  ->  enrich from Gelato (live)  ->  validate images
        ->  diff vs the previous snapshot  ->  re-apply preserved custom data
        ->  save snapshot  ->  emit a daily audit report

Design invariants (the safety contract):
  * TEST_MODE / no key -> the LIVE Gelato pull is a no-op. The local snapshot is
    still rebuilt from our in-code catalog, so the derived views (Men's, Women's,
    New arrivals, Best sellers) render for review without ever calling Gelato.
  * The sync NEVER overwrites the owner's custom data. Custom categories, SEO
    metadata, product rankings and custom descriptions live in a SEPARATE
    overrides file that the sync only READS and re-applies.
  * Nothing is fabricated. "Best sellers" come from owner-curated rankings or real
    order counts - never an invented "bestseller" badge pre-launch. On the first
    snapshot, products are seeded as the baseline, not flagged as "new arrivals".

The local DB lives under OUTPUT_DIR/catalog/ (products.json, overrides.json,
audit/<date>.txt).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

# A product is a "new arrival" if first seen within this many days (and not part
# of the initial baseline seed).
NEW_ARRIVAL_DAYS = 30
# Minimum acceptable longest edge for a product image (px) - smaller reads as a
# broken/placeholder thumbnail, not a real product shot.
MIN_IMAGE_EDGE = 400


# ── Local product DB paths ───────────────────────────────────────

def _catalog_dir() -> Path:
    """Directory holding the local product DB, overrides and audit history."""
    from quoteforge.config import OUTPUT_DIR
    return Path(OUTPUT_DIR) / "catalog"


def _snapshot_path() -> Path:
    """Path to the local product snapshot (the website's fast read source)."""
    return _catalog_dir() / "products.json"


def _overrides_path() -> Path:
    """Path to the owner's PRESERVED custom data (categories/SEO/rank/description).
    The sync only reads this file - it is never written by a sync."""
    return _catalog_dir() / "overrides.json"


def load_snapshot() -> dict:
    """Read the local product snapshot; empty skeleton if missing/corrupt."""
    p = _snapshot_path()
    if not p.exists():
        return {"synced_at": None, "products": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a corrupt snapshot must not break a sync
        return {"synced_at": None, "products": {}}


def save_snapshot(products: dict, *, when: str | None = None) -> Path:
    """Write the product snapshot (with a sync timestamp) and return its path."""
    p = _snapshot_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = when or datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps({"synced_at": stamp, "products": products},
                            indent=2, sort_keys=True), encoding="utf-8")
    return p


def load_overrides() -> dict:
    """Read the owner's custom overrides (empty if none). Keyed by product id ->
    {category, seo, rank, description}. Never modified by the sync."""
    p = _overrides_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


# ── Build the local catalog from our in-code source of truth ─────

def build_local_catalog() -> dict:
    """Build the baseline product records from our OWN catalog (apparel garments),
    independent of any network call. This is the always-available local DB the
    website can read; Gelato enrichment layers real images/pricing on top when
    live. Keyed by garment_id."""
    out: dict = {}
    try:
        from quoteforge.etsy.apparel_catalog import (
            APPAREL_CATALOG, build_apparel_variations)
    except Exception:  # noqa: BLE001
        return out
    # cheapest live-priced variant per garment (re-derives the 60% floor)
    price_from: dict = {}
    cost_from: dict = {}
    for v in build_apparel_variations():
        if v.price is not None:
            price_from[v.garment_id] = min(price_from.get(v.garment_id, 1e9), v.price)
        if v.gelato_cost is not None:
            cost_from[v.garment_id] = min(cost_from.get(v.garment_id, 1e9),
                                          v.gelato_cost)
    for g in APPAREL_CATALOG:
        if g.garment_id not in price_from:
            continue                       # discontinued -> not sellable -> skip
        brand = g.brand.rsplit(" ", 1)[0] if g.brand else ""   # drop style code
        out[g.garment_id] = {
            "id": g.garment_id,
            "name": g.name,
            "type": g.garment_type,
            "type_name": g.type_name,
            "gender": g.gender,
            "tier": g.tier,
            "brand": brand,
            "colors": list(g.colors),
            "sizes": list(g.sizes),
            "cost": round(cost_from.get(g.garment_id, g.base_cost), 2),
            "price": round(price_from[g.garment_id], 2),
            "available": True,
            "image": "",                   # filled by enrich_from_gelato when live
            "mockups": {},
        }
    # Branded products (Custom Branded Products dept) — same baseline treatment.
    try:
        from quoteforge.etsy.branded_catalog import (
            BRANDED_CATALOG, build_branded_variations)
    except Exception:  # noqa: BLE001
        return out
    b_price_from: dict = {}
    b_cost_from: dict = {}
    for v in build_branded_variations():
        if v.price is not None:
            b_price_from[v.product_id] = min(b_price_from.get(v.product_id, 1e9), v.price)
        if v.gelato_cost is not None:
            b_cost_from[v.product_id] = min(b_cost_from.get(v.product_id, 1e9),
                                            v.gelato_cost)
    for p in BRANDED_CATALOG:
        if p.product_id not in b_price_from:
            continue                       # discontinued -> not sellable -> skip
        brand = p.brand.rsplit(" ", 1)[0] if p.brand else ""   # drop style code
        out[p.product_id] = {
            "id": p.product_id,
            "name": p.name,
            "type": "branded",
            "type_name": p.type_name,
            "gender": "",
            "tier": p.tier,
            "brand": brand,
            "colors": list(p.colors),
            "sizes": list(p.sizes),
            "cost": round(b_cost_from.get(p.product_id, p.base_cost), 2),
            "price": round(b_price_from[p.product_id], 2),
            "available": True,
            "image": "",                   # filled by enrich_from_gelato when live
            "mockups": {},
        }
    # Mugs (Custom Mugs dept) — same baseline treatment.
    try:
        from quoteforge.etsy.mug_catalog import (
            MUG_CATALOG, build_mug_variations)
    except Exception:  # noqa: BLE001
        return out
    m_price_from: dict = {}
    m_cost_from: dict = {}
    for v in build_mug_variations():
        if v.price is not None:
            m_price_from[v.product_id] = min(m_price_from.get(v.product_id, 1e9), v.price)
        if v.gelato_cost is not None:
            m_cost_from[v.product_id] = min(m_cost_from.get(v.product_id, 1e9),
                                            v.gelato_cost)
    for p in MUG_CATALOG:
        if p.product_id not in m_price_from:
            continue                       # discontinued -> not sellable -> skip
        brand = p.brand.rsplit(" ", 1)[0] if p.brand else ""   # drop style code
        out[p.product_id] = {
            "id": p.product_id,
            "name": p.name,
            "type": "mug",
            "type_name": p.type_name,
            "gender": "",
            "tier": p.tier,
            "brand": brand,
            "colors": list(p.colors),
            "sizes": list(p.sizes),
            "cost": round(m_cost_from.get(p.product_id, p.base_cost), 2),
            "price": round(m_price_from[p.product_id], 2),
            "available": True,
            "image": "",                   # filled by enrich_from_gelato when live
            "mockups": {},
        }
    # Calendars (Custom Calendars dept) — same baseline treatment.
    try:
        from quoteforge.etsy.calendar_catalog import (
            CALENDAR_CATALOG, build_calendar_variations)
    except Exception:  # noqa: BLE001
        return out
    c_price_from: dict = {}
    c_cost_from: dict = {}
    for v in build_calendar_variations():
        if v.price is not None:
            c_price_from[v.product_id] = min(c_price_from.get(v.product_id, 1e9), v.price)
        if v.gelato_cost is not None:
            c_cost_from[v.product_id] = min(c_cost_from.get(v.product_id, 1e9),
                                            v.gelato_cost)
    for p in CALENDAR_CATALOG:
        if p.product_id not in c_price_from:
            continue                       # discontinued -> not sellable -> skip
        brand = p.brand.rsplit(" ", 1)[0] if p.brand else ""   # drop style code
        out[p.product_id] = {
            "id": p.product_id,
            "name": p.name,
            "type": "calendar",
            "type_name": p.type_name,
            "gender": "",
            "tier": p.tier,
            "brand": brand,
            "colors": list(p.colors),
            "sizes": list(p.sizes),
            "cost": round(c_cost_from.get(p.product_id, p.base_cost), 2),
            "price": round(c_price_from[p.product_id], 2),
            "available": True,
            "image": "",                   # filled by enrich_from_gelato when live
            "mockups": {},
        }
    return out


# ── Live Gelato enrichment (no-op in TEST_MODE / without a key) ──

def _is_live() -> bool:
    """True only when a genuine live sync is allowed (not TEST_MODE, key present)."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return not TEST_MODE and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


def enrich_from_gelato(records: dict, *, refresh_images: bool = False) -> dict:
    """Layer REAL Gelato data (product image, availability, latest cost) onto the
    local records, in place. No-op in TEST_MODE / without a key, so the local
    catalog stands alone for review. Never raises - a network blip leaves the
    baseline record untouched."""
    if not _is_live():
        return records
    try:
        from quoteforge.images.supplier_mockup import gelato_blank_image
        from quoteforge.etsy.apparel_catalog import apparel_sku_for, get_garment
        from quoteforge.etsy.catalog_state import sku_override
    except Exception:  # noqa: BLE001
        return records
    for gid, rec in records.items():
        g = get_garment(gid)
        if not g or not (g.sizes and g.colors):
            continue
        sku = apparel_sku_for(gid, g.sizes[0], g.colors[0])
        if not sku:
            continue
        try:
            url = gelato_blank_image(sku, refresh=refresh_images)
            if url:
                rec["image"] = url
            ov = sku_override(sku)
            if ov.get("available") is False:
                rec["available"] = False
            if ov.get("cost") is not None:
                rec["cost"] = round(ov["cost"], 2)
        except Exception:  # noqa: BLE001 — one product's blip can't fail the sync
            continue
    return records


# ── Diff detection ───────────────────────────────────────────────

def diff_catalog(old: dict, new: dict) -> dict:
    """Compare two product maps (id -> record) and classify the changes the audit
    report cares about: added, discontinued, price_changes, new_colors, new_sizes
    and image_changes. Pure - no side effects."""
    old = old or {}
    new = new or {}
    added = [k for k in new if k not in old]
    discontinued = [k for k in old if k not in new
                    or (new.get(k, {}).get("available") is False
                        and old.get(k, {}).get("available") is not False)]
    price_changes, new_colors, new_sizes, image_changes, updated = [], [], [], [], []
    for k in new:
        if k not in old:
            continue
        o, n = old[k], new[k]
        changed = False
        if o.get("price") != n.get("price"):
            price_changes.append({"id": k, "from": o.get("price"),
                                  "to": n.get("price")})
            changed = True
        fresh_c = [c for c in (n.get("colors") or []) if c not in (o.get("colors") or [])]
        if fresh_c:
            new_colors.append({"id": k, "colors": fresh_c})
            changed = True
        fresh_s = [s for s in (n.get("sizes") or []) if s not in (o.get("sizes") or [])]
        if fresh_s:
            new_sizes.append({"id": k, "sizes": fresh_s})
            changed = True
        if (o.get("image") or "") != (n.get("image") or ""):
            image_changes.append(k)
            changed = True
        if changed:
            updated.append(k)
    return {"added": added, "updated": updated, "discontinued": discontinued,
            "price_changes": price_changes, "new_colors": new_colors,
            "new_sizes": new_sizes, "image_changes": image_changes}


# ── Image validation ─────────────────────────────────────────────

def validate_image(src: str, *, expect_id: str | None = None) -> dict:
    """Validate one product image: that it loads, meets MIN_IMAGE_EDGE, and (when
    `expect_id` is given) that a local filename maps to the expected product.
    Accepts a local path or an http(s) URL (downloaded when live). Returns
    {'ok': bool, 'reason': str|None, 'size': [w,h]|None}. Never raises."""
    if not src:
        return {"ok": False, "reason": "missing", "size": None}
    try:
        from PIL import Image
        import io
        data: bytes | None = None
        if src.lower().startswith(("http://", "https://")):
            if not _is_live():
                return {"ok": True, "reason": "skipped (offline)", "size": None}
            import requests
            r = requests.get(src, timeout=20)
            if r.status_code != 200:
                return {"ok": False, "reason": f"http {r.status_code}", "size": None}
            data = r.content
        else:
            p = Path(src)
            if not p.exists():
                return {"ok": False, "reason": "file missing", "size": None}
            data = p.read_bytes()
        im = Image.open(io.BytesIO(data))
        im.verify()                                   # detects truncated/broken
        w, h = Image.open(io.BytesIO(data)).size      # re-open after verify()
        if max(w, h) < MIN_IMAGE_EDGE:
            return {"ok": False, "reason": f"too small {w}x{h}", "size": [w, h]}
        if expect_id and not src.lower().startswith(("http://", "https://")):
            stem = Path(src).stem.lower()
            if expect_id.lower() not in stem and stem not in expect_id.lower():
                return {"ok": False, "reason": f"maps to '{stem}' not '{expect_id}'",
                        "size": [w, h]}
        return {"ok": True, "reason": None, "size": [w, h]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"broken ({type(e).__name__})", "size": None}


def validate_images(records: dict) -> list[dict]:
    """Validate every record that carries an image; return the list of FAILURES
    only (empty = all good). Records without an image are skipped (the storefront
    falls back to its local tile)."""
    fails: list[dict] = []
    for gid, rec in (records or {}).items():
        src = rec.get("image") or ""
        if not src:
            continue
        res = validate_image(src, expect_id=gid)
        if not res["ok"]:
            fails.append({"id": gid, "src": src, "reason": res["reason"]})
    return fails


# ── Preserve owner custom data + derived views ───────────────────

def apply_overrides(records: dict, overrides: dict) -> dict:
    """Re-apply the owner's PRESERVED custom data (category, SEO, rank, custom
    description) onto the freshly-synced records, in place. The sync controls
    catalog facts (price, colours, images); the owner controls merchandising."""
    for gid, ov in (overrides or {}).items():
        rec = records.get(gid)
        if not rec or not isinstance(ov, dict):
            continue
        for field in ("category", "seo", "rank", "description"):
            if ov.get(field) is not None:
                rec[field] = ov[field]
    return records


def build_catalog_views(records: dict, *, today: str | None = None) -> dict:
    """Derive the merchandising catalogs the website shows: men's, women's, new
    arrivals and best sellers. Honest by construction - new arrivals come from
    first_seen dates, best sellers from owner rank (never a fabricated badge)."""
    recs = list((records or {}).values())
    now = datetime.fromisoformat(today) if today else datetime.now()
    cutoff = now - timedelta(days=NEW_ARRIVAL_DAYS)

    def _is_new(r: dict) -> bool:
        """True if first seen within the window and not a baseline-seed product."""
        fs = r.get("first_seen")
        if not fs or r.get("baseline"):
            return False
        try:
            return datetime.fromisoformat(fs) >= cutoff
        except Exception:  # noqa: BLE001
            return False

    mens = [r for r in recs if r.get("gender") == "men"]
    womens = [r for r in recs if r.get("gender") == "women"]
    new_arrivals = [r for r in recs if _is_new(r)]
    ranked = [r for r in recs if isinstance(r.get("rank"), (int, float))]
    best = sorted(ranked, key=lambda r: r["rank"])      # owner-curated only
    return {"mens": mens, "womens": womens,
            "new_arrivals": new_arrivals, "best_sellers": best}


# ── The nightly feedback loop ────────────────────────────────────

def sync_catalog_full(*, refresh_images: bool = False,
                      today: str | None = None) -> dict:
    """Run the full nightly loop and return an audit report dict.

    Steps: build local catalog -> enrich from Gelato (live) -> validate images ->
    diff vs the previous snapshot -> stamp first_seen/last_seen -> re-apply the
    owner's preserved overrides -> save the snapshot. TEST_MODE-safe: the live
    enrichment is skipped, but the local DB is still rebuilt so the views render.
    """
    stamp = today or datetime.now().isoformat(timespec="seconds")
    day = stamp[:10]
    prev = load_snapshot()
    prev_products = prev.get("products", {})
    first_run = not prev_products

    records = build_local_catalog()
    enrich_from_gelato(records, refresh_images=refresh_images)

    # Carry first_seen forward; stamp genuinely-new products with today's date.
    # On the very first run everything is the BASELINE seed (not "new arrivals").
    for gid, rec in records.items():
        old = prev_products.get(gid, {})
        rec["first_seen"] = old.get("first_seen") or day
        rec["last_seen"] = day
        if first_run:
            rec["baseline"] = True
        elif gid not in prev_products:
            rec["first_seen"] = day        # truly new since the last snapshot

    image_fails = validate_images(records)
    diff = diff_catalog(prev_products, records)
    apply_overrides(records, load_overrides())
    save_snapshot(records, when=stamp)

    return {
        "live": _is_live(),
        "first_run": first_run,
        "synced_at": stamp,
        "checked": len(records),
        "added": len(diff["added"]),
        "updated": len(diff["updated"]),
        "discontinued": len(diff["discontinued"]),
        "image_changes": len(diff["image_changes"]),
        "price_changes": diff["price_changes"],
        "new_colors": diff["new_colors"],
        "new_sizes": diff["new_sizes"],
        "image_failures": image_fails,
        "added_ids": diff["added"],
        "discontinued_ids": diff["discontinued"],
    }


def format_catalog_audit(r: dict) -> str:
    """Render the daily catalog-sync audit as a short plain-text block:
    products added/updated, images updated, price changes and sync failures."""
    mode = "LIVE" if r.get("live") else "TEST_MODE (local rebuild only, no Gelato call)"
    lines = ["Gelato catalog sync — daily audit", "=" * 40,
             f"  When         : {r.get('synced_at', '')}",
             f"  Mode         : {mode}",
             f"  Products      : {r.get('checked', 0)} in catalog",
             f"  Products Added: {r.get('added', 0)}",
             f"  Products Updated: {r.get('updated', 0)}",
             f"  Discontinued : {r.get('discontinued', 0)}",
             f"  Images Updated: {r.get('image_changes', 0)}",
             f"  Price Changes: {len(r.get('price_changes', []))}"]
    for pc in r.get("price_changes", [])[:8]:
        lines.append(f"    - {pc['id']}: ${pc['from']} -> ${pc['to']}")
    nc = r.get("new_colors", [])
    if nc:
        lines.append(f"  New Colours  : {sum(len(x['colors']) for x in nc)} "
                     f"across {len(nc)} product(s)")
    ns = r.get("new_sizes", [])
    if ns:
        lines.append(f"  New Sizes    : {sum(len(x['sizes']) for x in ns)} "
                     f"across {len(ns)} product(s)")
    fails = r.get("image_failures", [])
    lines.append(f"  Sync Failures: {len(fails)} image issue(s)")
    for f in fails[:8]:
        lines.append(f"    ! {f['id']}: {f['reason']} ({f['src'][:60]})")
    if r.get("first_run"):
        lines.append("  (baseline seed - products not flagged as new arrivals)")
    return "\n".join(lines)


def persist_audit(text: str, *, today: str | None = None) -> Path:
    """Write the audit text to OUTPUT_DIR/catalog/audit/<date>.txt and return it."""
    day = (today or datetime.now().isoformat())[:10]
    d = _catalog_dir() / "audit"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{day}.txt"
    p.write_text(text, encoding="utf-8")
    return p
