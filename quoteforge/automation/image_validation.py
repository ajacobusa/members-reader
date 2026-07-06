"""Automated image validation - evidence-based approval of synced Etsy/Gelato product
images, replacing manual user review. The system auto-approves HIGH-CONFIDENCE images and
only alerts when an image cannot be PROVEN correct.

Honest split (grounded, no fake detectors):
  * DETERMINISTIC checks run on the real image bytes with PIL and are fully verifiable:
    reachable, valid file, not blank, minimum resolution, aspect ratio vs the product family,
    not a duplicate (average-hash). These form the backbone confidence score.
  * PRODUCT DETECTION / studio-vs-lifestyle classification genuinely needs a vision model.
    It is an INJECTABLE, live-gated signal (like the print-QA vision step) - never a faked
    shape heuristic. When it is unavailable (TEST_MODE / no backend) a REQUIRED image
    (rank 1/2) cannot AUTO_APPROVE; it is held NEEDS_REVIEW rather than rubber-stamped.

Verdicts: AUTO_APPROVED (score >= threshold + required checks pass) / NEEDS_REVIEW / BLOCKED
(a critical check failed). A listing publish is blocked unless image 1 AND image 2 are
AUTO_APPROVED (never rely on rank alone: rank + analysis + metadata).
"""
from __future__ import annotations

import io
import json
import logging

logger = logging.getLogger(__name__)

_MIN_W, _MIN_H = 1500, 1500          # Etsy recommends >= 2000px; 1500 is a hard floor.
_AUTO_APPROVE_SCORE = 0.95
_DUP_HAMMING = 5                     # <= this average-hash distance == duplicate.
# Expected aspect ratio (w/h) window per family. Loose - just catches a wrong-shape image.
_FAMILY_ASPECT = {
    "apparel": (0.6, 1.15),          # portrait-ish product shots
    "mug": (0.75, 1.4),
    "branded": (0.6, 1.6),
    "calendar": (0.6, 1.6),
    "wall-art": (0.4, 1.8),          # posters/canvas vary widely by size
}
_CRITICAL = ("valid_file", "not_blank", "resolution_ok")


def _ahash(img) -> str:
    """8x8 average-hash of an image -> 16-hex string, for near-duplicate detection."""
    g = img.convert("L").resize((8, 8))
    px = list(g.tobytes())
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p >= avg:
            bits |= (1 << i)
    return f"{bits:016x}"


def _hamming(h1: str, h2: str) -> int:
    """Hamming distance between two hex average-hashes (bit differences)."""
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except Exception:  # noqa: BLE001
        return 64


def _classify(rank: int, detected_family: str | None) -> str:
    """Assign an image type from rank + (when available) the detected content. Rank is the
    prior (1=studio, 2=lifestyle, 3+=mockup); a detector result can override to size_chart
    or unknown so we never trust rank alone."""
    if detected_family in ("size_chart", "unknown"):
        return detected_family
    return {1: "studio", 2: "lifestyle"}.get(int(rank or 0), "mockup")


def validate_image_bytes(data: bytes, *, family: str = "", rank: int = 0,
                         seen_hashes=None, min_w: int = _MIN_W, min_h: int = _MIN_H,
                         reachable: bool = True, detector=None) -> dict:
    """Validate one image's raw bytes. Returns {checks, score, status, classification, ahash}.
    Deterministic + optional injected `detector(data, family)->str|None` (the product it sees,
    or None). Never raises."""
    from PIL import Image
    checks: dict = {"reachable": bool(reachable)}
    img = None
    ahash = ""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        checks["valid_file"] = True
    except Exception as exc:  # noqa: BLE001 - broken/невalid file
        logger.debug("image not a valid file: %s", exc)
        checks["valid_file"] = False

    if img is not None:
        w, h = img.size
        checks["not_blank"] = _not_blank(img)
        checks["resolution_ok"] = (w >= min_w and h >= min_h)
        checks["aspect_ok"] = _aspect_ok(w, h, family)
        ahash = _ahash(img)
        checks["not_duplicate"] = all(_hamming(ahash, s) > _DUP_HAMMING
                                      for s in (seen_hashes or []))
    else:
        checks.update({"not_blank": False, "resolution_ok": False,
                       "aspect_ok": False, "not_duplicate": True})

    detected = None
    if detector is not None and checks["valid_file"]:
        try:
            detected = detector(data, family)
        except Exception as exc:  # noqa: BLE001 - a detector error is not a pass
            logger.warning("image detector failed: %s", exc)
            detected = None
        # product_detected == the detector confirms our family (not size_chart/unknown/other)
        checks["product_detected"] = (detected == family)

    evaluated = [v for v in checks.values() if isinstance(v, bool)]
    score = round(sum(1 for v in evaluated if v) / len(evaluated), 4) if evaluated else 0.0

    critical_ok = all(checks.get(k) for k in _CRITICAL)
    required = int(rank or 0) in (1, 2)
    if not critical_ok:
        status = "BLOCKED"
    elif score >= _AUTO_APPROVE_SCORE and (not required or checks.get("product_detected") is True):
        status = "AUTO_APPROVED"
    elif required:
        # a required image we can't fully prove (low score, or product not confirmed) is
        # never auto-approved - held for review rather than rubber-stamped.
        status = "NEEDS_REVIEW"
    else:
        status = "AUTO_APPROVED" if score >= _AUTO_APPROVE_SCORE else "NEEDS_REVIEW"

    return {"checks": checks, "score": score, "status": status,
            "classification": _classify(rank, detected), "ahash": ahash}


def _not_blank(img) -> bool:
    """True if the image has real content (grayscale std above a floor). A flat/near-flat
    image (all white/black/one colour) is blank."""
    try:
        g = img.convert("L").resize((32, 32))
        px = list(g.tobytes())
        mean = sum(px) / len(px)
        var = sum((p - mean) ** 2 for p in px) / len(px)
        return var ** 0.5 > 3.0
    except Exception:  # noqa: BLE001
        return False


def _aspect_ok(w: int, h: int, family: str) -> bool:
    """True if w/h sits within the family's expected aspect window (loose)."""
    if not h:
        return False
    lo, hi = _FAMILY_ASPECT.get((family or "").strip().lower(), (0.3, 2.0))
    return lo <= (w / h) <= hi


# ── Orchestration over a live Etsy listing ───────────────────────

def _live() -> bool:
    """True only when genuinely live (TEST_MODE off + a Gelato key present)."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return (not TEST_MODE) and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


def _record(row: dict) -> None:
    """Upsert one image_validation result (keyed on etsy_image_id)."""
    from quoteforge.db.database import _conn
    with _conn() as conn:
        conn.execute("""
            INSERT INTO image_validation (product_id, product_family, etsy_image_id, image_url,
                image_rank, classification, checks_json, score, status, ahash, validated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(etsy_image_id) DO UPDATE SET
              product_id=excluded.product_id, product_family=excluded.product_family,
              image_url=excluded.image_url, image_rank=excluded.image_rank,
              classification=excluded.classification, checks_json=excluded.checks_json,
              score=excluded.score, status=excluded.status, ahash=excluded.ahash,
              validated_at=datetime('now')
        """, (row["product_id"], row["family"], row["etsy_image_id"], row["image_url"],
              row["rank"], row["classification"], json.dumps(row["checks"]), row["score"],
              row["status"], row["ahash"]))


def validate_synced_images(product_id: str, family: str, listing_id: str, *,
                           fetcher=None, downloader=None, detector=None) -> dict:
    """Validate every image of an Etsy listing and store the verdicts. Returns
    {images, auto_approved, blocked, needs_review, required_ok}. `fetcher(listing_id)->
    [{listing_image_id, url_fullxfull, rank}]`, `downloader(url)->bytes`, and `detector`
    are injectable (default to live Etsy + HTTP). No-op-safe: with no fetcher and not live,
    returns an empty result rather than guessing."""
    fetch = fetcher or _etsy_images
    if fetcher is None and not _live():
        return {"images": 0, "skipped": "not live", "required_ok": False}
    imgs = sorted(fetch(listing_id) or [], key=lambda i: (i or {}).get("rank", 99))
    dl = downloader or _download
    seen: list[str] = []
    results: list[dict] = []
    for im in imgs:
        url = (im or {}).get("url_fullxfull") or (im or {}).get("url") or ""
        rank = int((im or {}).get("rank") or 0)
        reachable, data = True, b""
        try:
            data = dl(url) or b""
            reachable = bool(data)
        except Exception as exc:  # noqa: BLE001 - unreachable/broken -> a failed check
            logger.warning("image download failed %s: %s", url, exc)
            reachable = False
        v = validate_image_bytes(data, family=family, rank=rank, seen_hashes=seen,
                                 reachable=reachable, detector=detector)
        if v["ahash"]:
            seen.append(v["ahash"])
        _record({"product_id": product_id, "family": family,
                 "etsy_image_id": str((im or {}).get("listing_image_id") or url),
                 "image_url": url, "rank": rank, **v})
        results.append({"rank": rank, "status": v["status"], "score": v["score"]})

    by_rank = {r["rank"]: r for r in results}
    required_ok = all(by_rank.get(k, {}).get("status") == "AUTO_APPROVED" for k in (1, 2))
    return {"images": len(results),
            "auto_approved": sum(1 for r in results if r["status"] == "AUTO_APPROVED"),
            "blocked": sum(1 for r in results if r["status"] == "BLOCKED"),
            "needs_review": sum(1 for r in results if r["status"] == "NEEDS_REVIEW"),
            "required_ok": required_ok, "results": results}


def required_images_ok(product_id: str) -> bool:
    """Publish gate: True only when image 1 AND image 2 for a product are AUTO_APPROVED."""
    from quoteforge.db.database import _conn
    with _conn() as conn:
        rows = conn.execute(
            "SELECT image_rank, status FROM image_validation WHERE product_id=? "
            "AND image_rank IN (1,2)", (product_id,)).fetchall()
    by = {int(r["image_rank"]): r["status"] for r in rows}
    return by.get(1) == "AUTO_APPROVED" and by.get(2) == "AUTO_APPROVED"


def _etsy_images(listing_id: str) -> list:
    """Live Etsy listing images (defensive). Empty on any error / no creds."""
    try:
        from quoteforge.automation.etsy_api import get_listing_images
        return get_listing_images(listing_id) or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("etsy image fetch failed (defensive): %s", exc)
        return []


def _download(url: str) -> bytes:
    """Fetch image bytes (defensive). Empty on any error."""
    if not url:
        return b""
    try:
        import requests
        resp = requests.get(url, timeout=30)
        return resp.content if resp.status_code == 200 else b""
    except Exception as exc:  # noqa: BLE001
        logger.warning("image download error %s: %s", url, exc)
        return b""
