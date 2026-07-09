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


# Per-category expectations for a usable BASE photo (orientation = w:h tendency).
_EXPECT = {
    "apparel": {"orientation": "portrait", "min_w": 800, "min_h": 800},
    "mug": {"orientation": "landscape-ish", "min_w": 600, "min_h": 600},
    "branded": {"orientation": "portrait", "min_w": 600, "min_h": 600},
}


def _rep_sku_uid(product_id: str, category: str) -> tuple[str, str]:
    """(representative SKU, its verified UID) for a manifest product - the first variant
    present in the approved export map ('' , '' when none, which excludes the row)."""
    from quoteforge.etsy.fulfillability import approved_export_map
    m = approved_export_map()
    skus: list = []
    if category == "apparel":
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
        g = next((x for x in APPAREL_CATALOG if x.garment_id == product_id), None)
        if g:
            skus = [apparel_sku_for(g.garment_id, s, c) or ""
                    for s in g.sizes for c in g.colors]
    elif category == "mug":
        from quoteforge.etsy.mug_catalog import MUG_CATALOG, _variant_sku
        p = next((x for x in MUG_CATALOG if x.product_id == product_id), None)
        if p:
            skus = [_variant_sku(p, s, c) for s in (p.sizes or [""])
                    for c in (p.colors or [""])]
    else:
        from quoteforge.etsy.branded_catalog import BRANDED_CATALOG, _variant_sku
        p = next((x for x in BRANDED_CATALOG if x.product_id == product_id), None)
        if p:
            skus = [_variant_sku(p, s, c)
                    for s in (getattr(p, "sizes", None) or [""])
                    for c in (getattr(p, "colors", None) or [""])]
    for sku in skus:
        uid = m.get(sku)
        if uid:
            return sku, uid
    return "", ""


def manifest() -> list[dict]:
    """The priority photo slots: top products per category that have a REAL verified UID.
    [{product_id, name, category, filename, rank, sku, gelato_uid, template_id,
    expected_orientation, min_w, min_h, makeable}] - rank is flagship-by-market order
    (pre-launch: market demand, not fabricated sales). Only UID-backed products appear,
    so every requested photo is for something we can actually sell. template_id is
    filled from the products table once the owner creates templates ('' until then)."""
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
    # Enrich every row: verified UID + representative SKU (the no-placeholder guarantee),
    # per-category expectations, and the template id once the owner has created one
    # (products table; '' until then). A row that somehow lost its UID is DROPPED -
    # the manifest can never request an unmakeable photo.
    out: list[dict] = []
    for row in rows:
        sku, uid = _rep_sku_uid(row["product_id"], row["category"])
        if not uid or str(uid).upper().startswith("GEL-"):
            continue
        exp = _EXPECT.get(row["category"], _EXPECT["branded"])
        tpl = ""
        try:
            from quoteforge.db.database import _conn
            with _conn() as conn:
                r = conn.execute(
                    "SELECT template_id FROM products WHERE gelato_sku=? "
                    "AND template_id IS NOT NULL AND template_id!='' LIMIT 1",
                    (sku,)).fetchone()
                tpl = (r[0] if r else "") or ""
        except Exception as exc:  # noqa: BLE001 - no DB/table yet: template unknown
            logger.debug("template lookup skipped for %s: %s", sku, exc)
        out.append({**row, "sku": sku, "gelato_uid": uid, "template_id": tpl,
                    "expected_orientation": exp["orientation"],
                    "min_w": exp["min_w"], "min_h": exp["min_h"], "makeable": True})
    return out


def _best_listing_image(images: dict, row: dict, downloader) -> tuple[bytes, str] | None:
    """Pick the best BASE photo from a listing's official images: prefer the rank-1
    studio image, fall back to lifestyle; each candidate must pass deterministic
    validation (decode / not-blank / resolution / aspect for the family). Returns
    (bytes, source_url) or None. Never raises."""
    from quoteforge.automation.image_validation import validate_image_bytes
    for key in ("studio", "lifestyle"):
        url = (images or {}).get(key)
        if not url:
            continue
        try:
            data = downloader(url)
        except Exception as exc:  # noqa: BLE001 - fetch blip: try the next candidate
            logger.debug("listing image fetch failed (%s): %s", key, exc)
            continue
        if not data:
            continue
        v = validate_image_bytes(data, family=row["category"],
                                 min_w=row["min_w"], min_h=row["min_h"])
        ch = v.get("checks", {})
        if ch.get("valid_file") and ch.get("not_blank") and ch.get("resolution_ok"):
            return data, url
    return None


def collect_from_etsy(*, listing_lookup=None, images_lookup=None,
                      downloader=None) -> dict:
    """The NO-HUMAN photo source: pull each manifest product's official images from its
    Gelato-published Etsy listing (documented Etsy API), validate deterministically, and
    save into the intake dir under the exact manifest filename - install() then places
    them for the storefront. Live-gated: without Etsy creds (or with no linked listings
    yet) it is a safe no-op that reports exactly what's missing. All IO injectable:
    ``listing_lookup(sku)->listing_id``, ``images_lookup(listing_id)->{studio,lifestyle}``,
    ``downloader(url)->bytes``. Never fabricates; a product with no valid listing image
    is reported, never guessed."""
    man = manifest()
    if listing_lookup is None:
        from quoteforge.db.database import existing_listing_id as listing_lookup  # type: ignore
    if images_lookup is None:
        from quoteforge.automation.etsy_api import official_listing_images as images_lookup  # type: ignore
    if downloader is None:
        def downloader(url: str) -> bytes:
            """Fetch one listing image (full-res) with a sane timeout."""
            import requests
            r = requests.get(url, timeout=30)
            return r.content if r.status_code == 200 else b""
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    collected, no_listing, no_image = [], [], []
    for row in man:
        target = INTAKE_DIR / row["filename"]
        if target.exists() or any(
                (MOCKUPS_DIR / f"{row['product_id']}{e}").exists()
                for e in (".jpg", ".png")):
            continue                                   # already sourced/installed
        lid = ""
        try:
            lid = listing_lookup(row["sku"]) or ""
        except Exception as exc:  # noqa: BLE001 - lookup blip counts as no listing
            logger.debug("listing lookup failed for %s: %s", row["sku"], exc)
        if not lid:
            no_listing.append(row["product_id"])
            continue
        best = _best_listing_image(images_lookup(lid) or {}, row, downloader)
        if not best:
            no_image.append(row["product_id"])
            continue
        data, src = best
        target.write_bytes(data)
        collected.append({"product_id": row["product_id"], "file": row["filename"],
                          "listing_id": str(lid), "source": "etsy_listing"})
    return {"collected": collected, "no_listing": no_listing, "no_image": no_image,
            "manifest": len(man)}


def selftest() -> dict:
    """Daily PASS/FAIL self-test of the whole real-photo path. Deterministic + hermetic
    (no network): manifest integrity (UID-backed, no placeholders, makeable), intake/
    installed slot coverage, and the display-path wiring (the same modules invariant #81
    certifies). FAIL only on a broken guarantee - missing photos pre-go-live are WAITING,
    not a failure (the collector fills them once listings exist)."""
    checks: list[dict] = []
    man = manifest()
    checks.append({"name": "manifest_uid_backed",
                   "ok": bool(man) and all(
                       r.get("gelato_uid") and not str(r["gelato_uid"]).upper()
                       .startswith("GEL-") and r.get("makeable") for r in man),
                   "detail": f"{len(man)} slots, all verified-UID + makeable"})
    st = status()
    checks.append({"name": "slot_coverage", "ok": True,       # informational, never FAIL
                   "detail": f"{len(st['installed'])}/{st['total']} installed, "
                             f"{len(st['waiting_install'])} in intake, "
                             f"{len(st['missing'])} awaiting collector"})
    try:
        import inspect
        from quoteforge.automation import customer_proof, image_validation
        ok = ("design_mockup_for_order" in inspect.getsource(customer_proof)
              and "get_listing_images" in inspect.getsource(image_validation))
        checks.append({"name": "display_path_wired", "ok": ok,
                       "detail": "proof composite + listing-image consumers wired"})
    except Exception as exc:  # noqa: BLE001 - missing symbol = broken wiring
        checks.append({"name": "display_path_wired", "ok": False, "detail": str(exc)})
    overall = all(c["ok"] for c in checks)
    return {"overall": "PASS" if overall else "FAIL", "checks": checks}


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
