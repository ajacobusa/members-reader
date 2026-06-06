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
from pathlib import Path

import requests

from quoteforge.config import (
    TEST_MODE, ETSY_API_BASE, ETSY_API_KEY, ETSY_OAUTH_TOKEN, ETSY_SHOP_ID,
    ETSY_TAXONOMY_ID, ETSY_SHIPPING_PROFILE_ID, ETSY_DEFAULT_LISTING_PRICE,
)


def _headers() -> dict:
    return {"x-api-key": ETSY_API_KEY,
            "Authorization": f"Bearer {ETSY_OAUTH_TOKEN}"}


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
    resp = runner.post(url, headers=_headers(), data=data, timeout=30)
    resp.raise_for_status()
    j = resp.json()
    return {"status": "draft_created", "listing_id": j.get("listing_id"),
            "title": bundle.title}


def upload_image(listing_id, image_path: Path, rank: int, runner=requests) -> bool:
    if TEST_MODE or prerequisites() or not listing_id:
        return False
    url = (f"{ETSY_API_BASE}/application/shops/{ETSY_SHOP_ID}"
           f"/listings/{listing_id}/images")
    with open(image_path, "rb") as fh:
        resp = runner.post(url, headers=_headers(),
                           files={"image": fh}, data={"rank": rank}, timeout=60)
    return resp.status_code in (200, 201)


def _gallery_for(kit_dir: Path, n: int) -> list[Path]:
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
