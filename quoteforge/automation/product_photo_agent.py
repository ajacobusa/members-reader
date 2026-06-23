"""Sheet-driven product-photo download agent.

Automates the "export a Gelato mockup -> get it onto the right product tile" chore so
the owner never hand-downloads or renames anything. The owner only pastes image URLs
into a sheet and marks them "Ready to Download"; this agent does the rest:

    Sheet row (Ready to Download)
      -> download mockup_image_url  (with retries)
      -> rename  tile-<product_id>.jpg
      -> save    brand/tile-<id>.jpg  (live tile)  AND  brand/product_photos/<YEAR>/<MONTH>/  (dated archive)
      -> update  image_status=Downloaded, local_file_name, last_downloaded_date
      -> log     missing / failed / duplicate

Works with any CSV/Google-Sheet export (Gelato, Etsy, Shopify) that has the columns
below. Network + filesystem + clock are injected, so the logic is fully unit-tested
without live calls. It never overwrites an existing (approved) tile unless told to.
"""
from __future__ import annotations

import csv
from pathlib import Path

REQUIRED_COLUMNS = [
    "product_id", "product_name", "gelato_product_url", "mockup_image_url",
    "image_status", "local_file_name", "last_downloaded_date", "notes",
]
READY = "Ready to Download"


def read_sheet(path) -> list[dict]:
    """Read a product CSV into a list of row dicts (empty list if absent)."""
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_sheet(path, rows: list[dict], columns: list[str] | None = None) -> None:
    """Write rows back to a CSV with the standard column order."""
    cols = columns or REQUIRED_COLUMNS
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def default_dest(brand_dir, product_id: str, now_iso: str) -> list[Path]:
    """Where a product photo is saved: the LIVE tile + a dated month/year archive."""
    brand = Path(brand_dir)
    fname = f"tile-{product_id}.jpg"
    year, month = (now_iso.split("-") + ["", ""])[:2]
    return [brand / fname,
            brand / "product_photos" / (year or "unknown") / (month or "00") / fname]


def download_url(url: str) -> bytes:
    """Live download of an image URL's bytes (raises on any non-200/network error)."""
    import requests
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def process_photo_sheet(rows: list[dict], download, dest_for, now_iso: str, *,
                        overwrite: bool = False, retries: int = 2, exists=None) -> dict:
    """Process every "Ready to Download" row. Mutates the row status fields in place.

    - ``download(url) -> bytes`` (raises on failure; retried ``retries`` times)
    - ``dest_for(product_id, now_iso) -> list[path]`` (live tile first, then archives)
    - ``exists(path) -> bool`` (defaults to ``Path(path).exists()``)

    Returns a summary with per-row log lines.
    """
    if exists is None:
        def exists(p):
            """Default existence check against the real filesystem."""
            return Path(p).exists()
    s = {"downloaded": 0, "failed": 0, "missing": 0, "exists": 0,
         "skipped": 0, "log": []}
    for r in rows:
        status = (r.get("image_status") or "").strip()
        pid = (r.get("product_id") or "").strip()
        if status != READY:
            s["skipped"] += 1
            continue
        url = (r.get("mockup_image_url") or "").strip()
        if not url:
            r["image_status"] = "Missing Image URL"
            s["missing"] += 1
            s["log"].append(f"{pid}: missing image_url")
            continue
        dests = dest_for(pid, now_iso)
        live = dests[0]
        if exists(live) and not overwrite:
            r["image_status"] = "Already Exists"
            s["exists"] += 1
            s["log"].append(f"{pid}: already exists ({Path(live).name}) - not overwritten")
            continue
        data, err = None, None
        for _ in range(retries + 1):
            try:
                data = download(url)
                break
            except Exception as exc:  # noqa: BLE001 - retried; recorded on final fail
                err = f"{type(exc).__name__}: {exc}"
        if data is None:
            r["image_status"] = "Failed"
            r["notes"] = err or "download failed"
            s["failed"] += 1
            s["log"].append(f"{pid}: FAILED ({err})")
            continue
        fname = f"tile-{pid}.jpg"
        for d in dests:
            dp = Path(d)
            dp.parent.mkdir(parents=True, exist_ok=True)
            dp.write_bytes(data)
        r["image_status"] = "Downloaded"
        r["local_file_name"] = fname
        r["last_downloaded_date"] = now_iso
        r["notes"] = ""
        s["downloaded"] += 1
        s["log"].append(f"{pid}: downloaded -> {fname}")
    return s


def build_template_rows(family_map: dict | None = None) -> list[dict]:
    """A ready-to-fill template row per product (so the owner just pastes URLs).

    Pre-fills product_id, product_name and (when mapped) gelato_product_url; leaves
    mockup_image_url blank and image_status='Needs URL'.
    """
    family_map = family_map or {}
    rows: list[dict] = []

    def add(pid, name, fam_key=""):
        """Append one ready-to-fill template row for a product."""
        rows.append({
            "product_id": pid, "product_name": name,
            "gelato_product_url": family_map.get(fam_key, ""),
            "mockup_image_url": "", "image_status": "Needs URL",
            "local_file_name": "", "last_downloaded_date": "", "notes": "",
        })

    try:
        from quoteforge.etsy.mug_catalog import MUG_CATALOG
        for p in MUG_CATALOG:
            add(p.product_id, p.name, f"mug:{p.product_id}")
    except Exception:  # noqa: BLE001
        pass
    try:
        from quoteforge.etsy.calendar_catalog import CALENDAR_CATALOG
        for p in CALENDAR_CATALOG:
            add(p.product_id, p.name, f"calendar:{p.product_id}")
    except Exception:  # noqa: BLE001
        pass
    try:
        from quoteforge.etsy.branded_catalog import BRANDED_CATALOG
        for p in BRANDED_CATALOG:
            add(p.product_id, p.name, f"branded:{p.product_id}")
    except Exception:  # noqa: BLE001
        pass
    try:
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
        seen = set()
        for g in APPAREL_CATALOG:
            if g.garment_id in seen:
                continue
            seen.add(g.garment_id)
            add(g.garment_id, g.name)
    except Exception:  # noqa: BLE001
        pass
    return rows
