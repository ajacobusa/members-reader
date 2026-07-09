"""Real product photo INTAKE - the owner-supplied path to the Gelato look-and-feel.

The public product API is imageless (live-proven: the full payload carries no image
field, and every mockup/image route 404s), so until the connected-store path activates
(GELATO_STORE_ID + first created product -> previewUrl, see real_images.py) the ONLY
sanctioned source of real product photos is the owner exporting them from their own
Gelato dashboard - a manual, ToS-clean act on their own account. This module makes
everything AROUND that one manual act automatic:

  * ``manifest()``  - the priority list: the top products per category that have a real
                      verified UID (flagship-by-market ranking - honest: we are pre-launch,
                      so "top" is market-demand ranking, never fabricated sales data).
  * ``intake dir``  - data/real_photos_intake/: the owner drops dashboard exports here
                      named <product_id>.jpg/png (the manifest prints the exact names).
  * ``install()``   - validates each intake file (decodes, sane size, not tiny), copies it
                      to brand/mockups/<product_id>.jpg (the path the storefront build
                      already consumes + composites), and reports per-file results.
  * ``status()``    - slots filled vs missing, so the daily report can nag until done.

Display is ALREADY implemented downstream: brand/mockups/<id>.jpg photos are discovered
by listing_preview's mockup_photos loader, re-emitted same-origin, and the editor
composites the buyer's design onto them (pinned by test_realphoto_mockup +
customer_image_paths invariant #81). This module only fills the slots.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

INTAKE_DIR = Path("data") / "real_photos_intake"
MOCKUPS_DIR = Path("brand") / "mockups"
_MIN_SIDE = 400            # a real product photo is at least this many px per side


def _mapped_garments() -> set:
    """Apparel garment families (base id, tier-stripped) with >=1 real approved UID."""
    from quoteforge.etsy.fulfillability import approved_export_map
    m = approved_export_map()
    out = set()
    for sku in m:
        if sku.startswith(("GEL-M-", "GEL-W-")):
            # GEL-M-TSHIRT-... -> m_tshirt (base garment; tiers share the photo)
            parts = sku.split("-")
            if len(parts) >= 3:
                out.add(f"{parts[1].lower()}_{parts[2].lower()}")
    return out


def manifest() -> list[dict]:
    """The priority photo slots: top products per category that have a REAL verified UID.
    [{product_id, name, category, filename, rank}] - rank is flagship-by-market order
    (pre-launch: market demand, not fabricated sales). Only UID-backed products appear,
    so every requested photo is for something we can actually sell."""
    from quoteforge.etsy.fulfillability import (fulfillable_mug_facets,
                                                fulfillable_branded_facets)
    from quoteforge.etsy.mug_catalog import MUG_CATALOG
    from quoteforge.etsy.branded_catalog import BRANDED_CATALOG
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    rows: list[dict] = []
    # APPAREL - top 8 garments by market demand, restricted to mapped families.
    apparel_rank = ["m_tshirt", "w_tshirt", "m_hoodie", "w_hoodie",
                    "m_sweatshirt", "m_longsleeve", "m_tank", "w_tank"]
    mapped = _mapped_garments()
    by_id = {g.garment_id: g for g in APPAREL_CATALOG}
    rank = 1
    for gid in apparel_rank:
        if gid in mapped and gid in by_id:
            rows.append({"product_id": gid, "name": by_id[gid].name,
                         "category": "apparel", "filename": f"{gid}.jpg", "rank": rank})
            rank += 1
    # MUGS - every mapped mug product (5 today; 8 variants), flagship order.
    mug_rank = ["classic_mug", "large_mug", "enamel_mug", "travel_mug", "xl_mug"]
    mugs = {p.product_id: p for p in MUG_CATALOG}
    rank = 1
    for pid in mug_rank:
        p = mugs.get(pid)
        if p is not None and fulfillable_mug_facets(p) is not None:
            rows.append({"product_id": pid, "name": p.name, "category": "mug",
                         "filename": f"{pid}.jpg", "rank": rank})
            rank += 1
    # BRANDED - every mapped product (tote today).
    rank = 1
    for p in BRANDED_CATALOG:
        if fulfillable_branded_facets(p):
            rows.append({"product_id": p.product_id, "name": p.name,
                         "category": "branded", "filename": f"{p.product_id}.jpg",
                         "rank": rank})
            rank += 1
    return rows


def _valid_photo(path: Path) -> tuple[bool, str]:
    """Decode-check a candidate photo: real image, sane dimensions. (ok, reason)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:              # verify() invalidates the handle
            w, h = im.size
        if min(w, h) < _MIN_SIDE:
            return False, f"too small ({w}x{h}; need >={_MIN_SIDE}px per side)"
        return True, f"{w}x{h}"
    except Exception as exc:  # noqa: BLE001 - not an image / corrupt
        return False, f"not a decodable image: {exc}"


def status() -> dict:
    """Slot coverage: which manifest photos are installed / awaiting intake / missing."""
    man = manifest()
    installed, waiting, missing = [], [], []
    for row in man:
        pid = row["product_id"]
        if any((MOCKUPS_DIR / f"{pid}{ext}").exists() for ext in (".jpg", ".png")):
            installed.append(pid)
        elif any((INTAKE_DIR / f"{pid}{ext}").exists()
                 for ext in (".jpg", ".jpeg", ".png")):
            waiting.append(pid)
        else:
            missing.append(pid)
    return {"total": len(man), "installed": installed, "waiting_install": waiting,
            "missing": missing}


def install() -> dict:
    """Validate + install every intake photo into brand/mockups/<product_id>.jpg
    (converting png->jpg name is NOT done: png is kept as .png - the loader accepts
    both). Only manifest product_ids are accepted (a stray file is reported, never
    installed), and a file that fails validation is left in intake + reported."""
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    MOCKUPS_DIR.mkdir(parents=True, exist_ok=True)
    valid_ids = {r["product_id"] for r in manifest()}
    installed, rejected, strangers = [], [], []
    for f in sorted(INTAKE_DIR.iterdir()):
        if not f.is_file() or f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        pid = f.stem.lower()
        if pid not in valid_ids:
            strangers.append(f.name)
            continue
        ok, detail = _valid_photo(f)
        if not ok:
            rejected.append({"file": f.name, "reason": detail})
            continue
        suffix = ".jpg" if f.suffix.lower() in (".jpg", ".jpeg") else ".png"
        dest = MOCKUPS_DIR / f"{pid}{suffix}"
        shutil.copyfile(f, dest)
        installed.append({"file": f.name, "dest": str(dest), "dims": detail})
    return {"installed": installed, "rejected": rejected, "unknown_files": strangers}


def format_manifest_text() -> str:
    """Owner-facing checklist: exact filenames to export from the dashboard."""
    st = status()
    lines = ["Real product photos - top UID-backed products per category",
             "=" * 62,
             f"Drop dashboard exports into {INTAKE_DIR}\\ named EXACTLY as below,",
             "then run: python -m quoteforge.admin real-photos install", ""]
    for row in manifest():
        pid = row["product_id"]
        mark = ("INSTALLED" if pid in st["installed"]
                else "IN INTAKE" if pid in st["waiting_install"] else "  needed ")
        lines.append(f"  [{mark}] {row['category']:<8} #{row['rank']} "
                     f"{row['filename']:<22} {row['name']}")
    lines.append("")
    lines.append(f"coverage: {len(st['installed'])}/{st['total']} installed, "
                 f"{len(st['waiting_install'])} awaiting install, "
                 f"{len(st['missing'])} needed")
    return "\n".join(lines)
