"""Auto-publish the launch listings to Etsy via the Open API.

Etsy v3 supports creating DRAFT listings and uploading images programmatically.
This reads the launch kit (SEO bundles + gallery images) and creates a draft
listing per item, uploads its 5 gallery images, and turns on personalization -
so the only manual step left is a final review + click 'Publish' in Etsy.

SAFE BY DEFAULT:
- Dry-run unless --live: prints exactly what WOULD be created, calls nothing.
- Creates DRAFTS, never auto-publishes (you review each before it goes live).
- No-ops with a clear prerequisites message until OAuth + shop IDs are set.

Prerequisites to go live (all from your shop, set in .env):
  ETSY_OAUTH_TOKEN (scope listings_w), ETSY_SHOP_ID, ETSY_API_KEY,
  ETSY_TAXONOMY_ID (wall-art prints), ETSY_SHIPPING_PROFILE_ID.
"""
import logging
from pathlib import Path

import requests

from quoteforge.config import (
    TEST_MODE, ETSY_API_BASE, ETSY_API_KEY, ETSY_OAUTH_TOKEN, ETSY_SHOP_ID,
    ETSY_TAXONOMY_ID, ETSY_SHIPPING_PROFILE_ID, ETSY_DEFAULT_LISTING_PRICE,
)

logger = logging.getLogger(__name__)


def _headers() -> dict:
    """Build Etsy v3 auth headers (API key + OAuth bearer token). Uses the FRESHEST
    access token (persisted, else the env seed) so a token refreshed mid-run is
    picked up on the retry — Etsy access tokens expire ~1h after issuance."""
    from quoteforge.automation.etsy_auth import current_access_token
    return {"x-api-key": ETSY_API_KEY,
            "Authorization": f"Bearer {current_access_token()}"}


def prerequisites() -> list[str]:
    """Return the list of MISSING prerequisites for live publishing."""
    need = {
        "ETSY_OAUTH_TOKEN (scope listings_w)": ETSY_OAUTH_TOKEN,
        "ETSY_SHOP_ID": ETSY_SHOP_ID,
        "ETSY_API_KEY": ETSY_API_KEY,
        "ETSY_TAXONOMY_ID": ETSY_TAXONOMY_ID,
        "ETSY_SHIPPING_PROFILE_ID": ETSY_SHIPPING_PROFILE_ID,
    }
    return [k for k, v in need.items() if not v]


def create_draft_listing(bundle, price: float, runner=requests) -> dict:
    """Create ONE Etsy draft listing from an SEO bundle. Mock unless live-ready."""
    if TEST_MODE or prerequisites():
        return {"status": "dry-run", "title": bundle.title,
                "tags": len(bundle.tags), "price": price}
    # IDEMPOTENCY (#182): a re-run must NOT create a duplicate Etsy listing. Key each
    # launch listing by launch-<n> (persisted in products) and reuse the prior id.
    from quoteforge.db.database import existing_listing_id, upsert_product
    _sku = f"launch-{getattr(bundle, 'n', '')}".rstrip("-")
    _prior = existing_listing_id(_sku)
    if _prior:
        return {"status": "exists", "listing_id": _prior, "title": bundle.title}
    url = f"{ETSY_API_BASE}/application/shops/{ETSY_SHOP_ID}/listings"
    data = {
        "quantity": 999, "title": bundle.title[:140],
        "description": bundle.description, "price": round(price, 2),
        "who_made": "i_did", "when_made": "made_to_order",
        "taxonomy_id": int(ETSY_TAXONOMY_ID),
        "shipping_profile_id": int(ETSY_SHIPPING_PROFILE_ID),
        "tags": ",".join(bundle.tags[:13]),
        "materials": ",".join(bundle.materials[:5]),
        "is_personalizable": "true", "personalization_is_required": "true",
        "personalization_instructions":
            "Recipient name, occasion, relationship, a short story, and "
            "(optional) your own exact wording.",
        "type": "physical", "state": "draft",
    }
    # On a 401 (token expired mid-run), refresh once and retry with the fresh token.
    from quoteforge.automation.etsy_auth import with_refresh
    def _post():
        """POST the draft with the CURRENT token; raise on non-2xx so with_refresh
        can catch a 401, refresh, and retry."""
        r = runner.post(url, headers=_headers(), data=data, timeout=30)
        r.raise_for_status()
        return r
    resp = with_refresh(_post)
    j = resp.json()
    _lid = j.get("listing_id")
    # Persist the SKU->listing map so the NEXT run dedupes (no duplicate listing).
    if _lid:
        try:
            upsert_product({"product_id": _sku, "gelato_sku": _sku,
                            "etsy_listing_id": str(_lid), "template_id": "",
                            "category": bundle.category, "title": bundle.title,
                            "price_usd": price, "gelato_cost_usd": 0.0,
                            "product_type": "print", "size": ""})
        except Exception as exc:  # noqa: BLE001 — mapping persist is best-effort
            logger.warning("listing map persist failed for %s: %s", _sku, exc)
    return {"status": "draft_created", "listing_id": _lid, "title": bundle.title}


# Etsy custom-property slots (a listing allows at most TWO variation axes).
_PROP_SIZE = 513
_PROP_FORMAT = 514


def _format_value(v) -> str:
    """One 'Format' axis value combining material + frame (Etsy's 2-axis limit
    means Material and Frame can't be separate axes alongside Size)."""
    from quoteforge.etsy.variations import MATERIAL_LABELS
    if v.material == "framed":
        return f"Framed - {v.frame_color}"
    return MATERIAL_LABELS[v.material].split(" (")[0]


def build_inventory_payload(floor_pct: int = None) -> dict:
    """Etsy inventory structure (2 axes: Size + Format) from the variation model,
    each offering priced at the 60% floor. Ready to PUT to the inventory API."""
    from quoteforge.etsy.variations import build_variations
    products = []
    for v in build_variations(floor_pct):
        products.append({
            "sku": v.gelato_sku,
            "property_values": [
                {"property_id": _PROP_SIZE, "property_name": "Size",
                 "values": [v.size]},
                {"property_id": _PROP_FORMAT, "property_name": "Format",
                 "values": [_format_value(v)]},
            ],
            "offerings": [{"price": round(v.price, 2), "quantity": 999,
                           "is_enabled": True}],
        })
    return {"products": products,
            "price_on_property": [_PROP_SIZE, _PROP_FORMAT],
            "quantity_on_property": [],
            "sku_on_property": [_PROP_SIZE, _PROP_FORMAT]}


def apparel_listing_garments() -> list[str]:
    """Garment ids that each become their OWN Etsy listing (apparel needs both
    variation axes for Size + Colour, so it can't share the wall-art listing)."""
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    return [g.garment_id for g in APPAREL_CATALOG]


def build_apparel_inventory_payload(garment_id: str, floor_pct: int = None) -> dict:
    """Etsy inventory for ONE apparel garment: Size (513) x Colour (514), each
    offering priced to clear the 60% floor. Apparel gets its own listing per
    garment because the print listing already spends both axes on Size + Format
    and Etsy allows only two. Ready to PUT to the inventory API.

    Emits garment / size / colour / price + the variant SKU ONLY - never a
    supplier name."""
    from quoteforge.etsy.apparel_catalog import build_apparel_variations
    products = []
    for v in build_apparel_variations(floor_pct):
        if v.garment_id != garment_id:
            continue
        products.append({
            "sku": v.gelato_sku,
            "property_values": [
                {"property_id": _PROP_SIZE, "property_name": "Size",
                 "values": [v.size]},
                {"property_id": _PROP_FORMAT, "property_name": "Color",
                 "values": [v.color]},
            ],
            "offerings": [{"price": round(v.price, 2), "quantity": 999,
                           "is_enabled": True}],
        })
    return {"products": products,
            "price_on_property": [_PROP_SIZE, _PROP_FORMAT],
            "quantity_on_property": [],
            "sku_on_property": [_PROP_SIZE, _PROP_FORMAT]}


def apply_variations(listing_id, live: bool = False, floor_pct: int = None,
                     runner=requests) -> dict:
    """Push the Size×Format variation matrix onto an Etsy listing.
    Dry-run unless live AND credentials present."""
    payload = build_inventory_payload(floor_pct)
    n = len(payload["products"])
    if not live or TEST_MODE or prerequisites() or not listing_id:
        return {"status": "dry-run", "variations": n,
                "axes": ["Size", "Format"]}
    url = f"{ETSY_API_BASE}/application/listings/{listing_id}/inventory"
    from quoteforge.automation.etsy_auth import refresh_access_token
    resp = runner.put(url, headers=_headers(), json=payload, timeout=60)
    if resp.status_code == 401 and refresh_access_token():
        resp = runner.put(url, headers=_headers(), json=payload, timeout=60)
    ok = resp.status_code in (200, 201)
    return {"status": "applied" if ok else f"error {resp.status_code}",
            "variations": n}


def upload_image(listing_id, image_path: Path, rank: int, runner=requests) -> bool:
    """Upload one listing image at the given rank; False unless live-ready."""
    if TEST_MODE or prerequisites() or not listing_id:
        return False
    url = (f"{ETSY_API_BASE}/application/shops/{ETSY_SHOP_ID}"
           f"/listings/{listing_id}/images")
    from quoteforge.automation.etsy_auth import refresh_access_token
    with open(image_path, "rb") as fh:
        resp = runner.post(url, headers=_headers(),
                           files={"image": fh}, data={"rank": rank}, timeout=60)
        if resp.status_code == 401 and refresh_access_token():
            fh.seek(0)
            resp = runner.post(url, headers=_headers(),
                               files={"image": fh}, data={"rank": rank}, timeout=60)
    return resp.status_code in (200, 201)


def _gallery_for(kit_dir: Path, n: int) -> list[Path]:
    """Find the gallery PNGs for launch-kit listing number `n`, sorted."""
    matches = list(kit_dir.glob(f"{n:02d}_*/gallery/*.png"))
    return sorted(matches)


def publish_launch_kit(live: bool = False, kit_dir=None, runner=requests) -> dict:
    """Create draft listings for all 20 launch listings (+ upload images if live)."""
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.etsy.listing_seo import build_launch_seo
    kit_dir = Path(kit_dir) if kit_dir else (OUTPUT_DIR / "launch_kit")
    missing = prerequisites()
    bundles = build_launch_seo()
    results = []
    for b in bundles:
        draft = create_draft_listing(b, ETSY_DEFAULT_LISTING_PRICE, runner) \
            if live else {"status": "dry-run", "title": b.title}
        imgs = _gallery_for(kit_dir, b.listing_n)
        uploaded = 0
        if live and draft.get("listing_id"):
            for rank, img in enumerate(imgs[:10], 1):
                if upload_image(draft["listing_id"], img, rank, runner):
                    uploaded += 1
        results.append({"n": b.listing_n, "title": b.title[:55],
                        "status": draft["status"], "images_found": len(imgs),
                        "images_uploaded": uploaded})
    return {"live": live, "missing_prereqs": missing,
            "count": len(results), "results": results}


def format_publish_text(r: dict) -> str:
    """Render the publish-run results as plain text, noting live vs dry-run."""
    mode = "LIVE (creating Etsy drafts)" if r["live"] else "DRY RUN (nothing sent)"
    lines = ["=" * 64, f"ETSY AUTO-PUBLISH - {mode}", "=" * 64]
    if r["missing_prereqs"]:
        lines.append("Cannot publish live yet. Missing prerequisites:")
        for m in r["missing_prereqs"]:
            lines.append(f"  - {m}")
        lines.append("")
    for x in r["results"]:
        lines.append(f"  [{x['status']:13}] #{x['n']:02d} {x['title']} "
                     f"({x['images_found']} imgs"
                     + (f", {x['images_uploaded']} uploaded" if r["live"] else "")
                     + ")")
    lines.append("\nDrafts are NOT auto-published - review each in Etsy, then "
                 "click Publish.")
    lines.append("=" * 64)
    return "\n".join(lines)
