"""Supplier product mockups — real product images for the storefront.

Pulls the actual product image the print partner ships for a garment, so a tile
can show what the customer receives instead of an AI approximation. Key-gated and
TEST_MODE-safe: with no API key or in TEST_MODE this returns None and the caller
falls back to the existing AI tile. Resolved URLs are cached to a JSON file so a
rebuild does not re-hit the API. It activates automatically once the owner sets
the key and maps real product UIDs (a placeholder GEL-* UID is treated as
unmapped, exactly like the go-live guard).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_PRODUCT_API = "https://product.gelatoapis.com/v3/products"


def _cache_path() -> Path:
    """Where resolved SKU->image-URL mappings are cached between rebuilds."""
    p = os.getenv("GELATO_MOCKUP_CACHE", "").strip()
    if p:
        return Path(p)
    from quoteforge.config import OUTPUT_DIR
    return Path(OUTPUT_DIR) / "gelato_mockups.json"


def _load_cache() -> dict:
    """Load the SKU->URL cache (empty dict if missing/unreadable)."""
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: dict) -> None:
    """Persist the SKU->URL cache; best-effort, never raises."""
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - cache is best-effort
        logger.debug("supplier-mockup cache write failed: %s", exc)


def _overrides_path() -> Path:
    """CSV of owner-supplied REAL product photos (cols: sku,url). Override with
    PRODUCT_IMAGE_OVERRIDES_FILE, else <repo>/config/product_image_overrides.csv."""
    env = os.getenv("PRODUCT_IMAGE_OVERRIDES_FILE", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "config" / "product_image_overrides.csv"


def product_photo_overrides() -> dict:
    """Owner-supplied REAL product photos as ``{our_sku: url}``.

    Lets the owner show the actual product picture for ANY product family WITHOUT
    going live - it bypasses Gelato's (imageless) catalog API and the TEST_MODE gate
    for DISPLAY only (never fulfilment). Read fresh each call (the file is tiny) so a
    just-edited manifest takes effect on the next rebuild; never raises. Storefront
    consumers re-host these same-origin (_emit_url), so no supplier URL leaks in
    view-source. Apparel needs only this URL (print geometry is computed); mug/branded/
    calendar instead use the brand/mockups/ file+sidecar path (they need geometry too).
    """
    out: dict = {}
    try:
        import csv
        p = _overrides_path()
        if not p.exists():
            return out
        with p.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                sku = (row.get("sku") or "").strip()
                url = (row.get("url") or "").strip()
                if sku.startswith("#"):                # comment row (copied example)
                    continue
                if sku and url.startswith(("http://", "https://")):
                    out[sku] = url
    except Exception as exc:  # noqa: BLE001 - a bad manifest must never break the build
        logger.debug("product photo overrides load failed: %s", exc)
    return out


def apparel_photo_override_keys() -> list[dict]:
    """The exact SKU keys the owner should fill in the override manifest for apparel,
    as ``[{sku, garment, color}]`` - one representative SKU per (garment, colour), keyed
    the SAME way the editor looks them up (first size per colour). So the owner never
    has to guess a SKU. Never raises."""
    rows: list[dict] = []
    try:
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
        for g in APPAREL_CATALOG:
            if not (g.sizes and g.colors):
                continue
            for color in g.colors:
                sku = apparel_sku_for(g.garment_id, g.sizes[0], color)
                if sku:
                    rows.append({"sku": sku, "garment": g.name, "color": color})
    except Exception as exc:  # noqa: BLE001
        logger.debug("apparel override keys failed: %s", exc)
    return rows


def _extract_image_url(data: dict) -> str | None:
    """Best-effort pull of a product preview/mockup image URL from a product API
    response. The field name varies across catalog products, so try the common
    shapes (flat url field, or the first entry of an images/mockups list)."""
    if not isinstance(data, dict):
        return None
    for key in ("previewUrl", "mockupUrl", "productImageUrl", "imageUrl", "image"):
        v = data.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    imgs = data.get("images") or data.get("mockups")
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, str) and first.startswith("http"):
            return first
        if isinstance(first, dict):
            for k in ("url", "previewUrl", "fileUrl", "imageUrl"):
                u = first.get(k)
                if isinstance(u, str) and u.startswith("http"):
                    return u
    return None


def _fetch_product_image(uid: str) -> str | None:
    """Live: one product's preview image URL (or None). Never raises."""
    import requests
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    try:
        r = requests.get(f"{_PRODUCT_API}/{uid}",
                         headers={"X-API-KEY": GELATO_API_KEY}, timeout=15)
        if r.status_code != 200:
            return None
        return _extract_image_url(r.json())
    except Exception:  # noqa: BLE001 — network/parse blip: fall back to AI tile
        return None


def gelato_blank_image_provenance(our_sku: str, *, refresh: bool = False) -> dict | None:
    """Real product image for our SKU WITH provenance, or None to fall back to the AI
    tile. Returns ``{"url", "uid", "source"}`` where ``uid`` is the Gelato UID the bytes
    are PROVABLY bound to (only the uid-map path can assert this), or ``None`` for the
    display-only shortcut sources whose origin UID we cannot prove:

      * ``override``   — owner-dropped CSV photo (display-only, uid unverifiable)
      * ``persisted``  — a prior template-sync DB row (carries its own uid if recorded)
      * ``ecommerce``  — connected-store previewUrl (uid unverifiable here)
      * ``uid_map``    — fetched from the Gelato product API for _uid_map()[sku] (uid PROVEN)

    Path A (mockup_sync) records this so ``confirm()`` can require a published image's
    origin UID to equal the SKU's resolved real UID — the "right product" guarantee. A
    None uid means "provenance unverified" → Path A holds it, never auto-publishes it.
    """
    # Owner-supplied real photo wins first (#realphotos): the owner can drop the actual
    # product picture per SKU into config/product_image_overrides.csv and see it NOW,
    # in TEST_MODE, bypassing the (imageless) catalog API. Display-only, never affects
    # fulfilment. Storefront consumers re-host it same-origin, so no supplier leak.
    _ov = product_photo_overrides().get((our_sku or "").strip())
    if _ov:
        return {"url": _ov, "uid": None, "source": "override"}
    from quoteforge.config import TEST_MODE
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    if TEST_MODE or not GELATO_API_KEY:
        return None
    # Prefer the DURABLY-persisted official image (#uidjoin fix): the daily template-sync
    # writes each product's real image into gelato_product_images and RETIRES stale ones,
    # so reading it here is what makes that persistence + stale-retire actually reach the
    # display (survives a transient store-API blip). Falls through if none persisted yet.
    try:
        from quoteforge.db.database import get_product_images
        _rows = get_product_images(our_sku)            # active, ranked
        if _rows and _rows[0].get("image_url"):
            return {"url": _rows[0]["image_url"],
                    "uid": _rows[0].get("gelato_product_uid"), "source": "persisted"}
    except Exception as exc:  # noqa: BLE001 — persisted lookup blip: try the live store
        logger.debug("persisted image lookup failed for %s: %s", our_sku, exc)
    # Then the connected ecommerce store's REAL product mockup (previewUrl) once the owner
    # creates a product (#180). Auto-activates with zero further wiring; returns {} until
    # then, so this falls through to the catalog path (kept for the test seam).
    try:
        from quoteforge.automation.ecommerce_images import images_by_sku
        _url = images_by_sku().get(our_sku)
        if _url:
            return {"url": _url, "uid": None, "source": "ecommerce"}
    except Exception as exc:  # noqa: BLE001 — ecommerce blip: fall back to catalog path
        logger.debug("ecommerce image lookup failed for %s: %s", our_sku, exc)
    from quoteforge.automation.gelato_sync import _uid_map
    uid = (_uid_map() or {}).get(our_sku)
    if not uid or str(uid).startswith("GEL-"):     # unmapped / placeholder seed
        return None
    # UID-BOUND cache (#uidremap): the cached image is a function of the UID, so the
    # entry records WHICH uid produced it. When the owner remaps a SKU to a new Gelato
    # UID (the whole point of the map), the cached uid no longer matches -> a MISS ->
    # refetch, instead of showing the OLD product forever. A legacy flat-string entry is
    # treated as a miss so it re-resolves once and upgrades to the uid-bound shape.
    cache = _load_cache()
    hit = cache.get(our_sku) if not refresh else None
    if isinstance(hit, dict) and hit.get("uid") == uid:
        return {"url": hit.get("url") or None, "uid": str(uid), "source": "uid_map"}
    url = _fetch_product_image(uid)
    cache[our_sku] = {"uid": uid, "url": url or ""}   # remember the uid it was resolved for
    _save_cache(cache)
    # url may be None (fetch blip) but the uid is proven — caller treats no-url as no image.
    return {"url": url, "uid": str(uid), "source": "uid_map"}


def gelato_blank_image(our_sku: str, *, refresh: bool = False) -> str | None:
    """Real product image URL for our SKU, or None to fall back to the AI tile.

    Returns None in TEST_MODE, without an API key, or for an unmapped / placeholder
    (GEL-*) UID — so nothing changes until the owner is genuinely live. Results are
    cached to JSON so a rebuild doesn't re-hit the API (pass refresh=True to force).
    Thin URL-only wrapper over ``gelato_blank_image_provenance`` (one source order).
    """
    prov = gelato_blank_image_provenance(our_sku, refresh=refresh)
    return (prov or {}).get("url") or None


def gelato_template_printarea(uid: str) -> dict | None:
    """Print placement for a product UID, as a fraction-of-photo rect for the mockup
    sync: ``{area:[x,y,w,h], cyl, span}`` or None.

    Gelato's Get-Template API exposes per-variant image placeholders with a
    ``printArea`` + ``height``/``width``. Mapping those onto the *mockup photo's*
    pixel rect is account/template-specific, so this is the documented seam:
    key-gated, returns None until the mapping is calibrated against a live account
    (the engine then falls back to the per-category geometry default, and the
    gelato-mockup-reviewer agent flags any product whose default is off). Never
    raises."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        if TEST_MODE or not GELATO_API_KEY or not uid or str(uid).startswith("GEL-"):
            return None
    except Exception:  # noqa: BLE001
        return None
    # Live print-area calibration (fetch the Gelato template, read printArea/dims,
    # map to the mockup-photo fraction rect) is a deferred enhancement that needs a
    # live Gelato account to build and verify; it is tracked as a separate work item
    # rather than guessed here. Until then the per-category geometry default is used,
    # and the gelato-mockup-reviewer agent flags any product whose default is off.
    return None


def apparel_tile_images(*, refresh: bool = False) -> dict:
    """Map garment_type -> real product image URL, one representative SKU per type
    (Classic tier, first colour/size). Only types that resolve to a real image are
    included; everything else stays on the AI tile. Empty in TEST_MODE / no key."""
    out: dict = {}
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        # Skip only when there is genuinely nothing to show: not live AND no owner
        # override manifest. When overrides exist, iterate so they surface in TEST_MODE
        # (gelato_blank_image returns the override, else None with no API call).
        if (TEST_MODE or not GELATO_API_KEY) and not product_photo_overrides():
            return out
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
    except Exception:  # noqa: BLE001
        return out
    for g in APPAREL_CATALOG:
        if not (g.sizes and g.colors):
            continue
        sku = apparel_sku_for(g.garment_id, g.sizes[0], g.colors[0])
        if not sku:
            continue
        url = gelato_blank_image(sku, refresh=refresh)
        if url:
            out[g.garment_id] = url             # PER GARMENT (tier/gender-exact)
    return out


def apparel_tile_color_images(*, refresh: bool = False) -> dict:
    """Map garment_id -> {colour -> real product image URL}, so each tile/editor
    shows the EXACT product for that garment (tier + gender) in the picked colour.
    One representative SKU per (garment, colour). Empty in TEST_MODE / no key (the
    tile keeps its default photo)."""
    out: dict = {}
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        # As above: iterate when an owner override manifest exists, so real photos show
        # in TEST_MODE too (per colour); otherwise skip when not live.
        if (TEST_MODE or not GELATO_API_KEY) and not product_photo_overrides():
            return out
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
    except Exception:  # noqa: BLE001
        return out
    for g in APPAREL_CATALOG:
        if not (g.sizes and g.colors):
            continue
        per_color: dict = {}
        for color in g.colors:
            sku = apparel_sku_for(g.garment_id, g.sizes[0], color)
            if sku:
                url = gelato_blank_image(sku, refresh=refresh)
                if url:
                    per_color[color] = url
        if per_color:
            out[g.garment_id] = per_color        # PER GARMENT (tier/gender-exact)
    return out


def _gelato_create_design_mockup(product_uid: str, design_url: str) -> str | None:
    """Ask Gelato to render the buyer's DESIGN on the product, returning the
    mockup image URL. DEFENSIVE provider seam: never raises, returns None on
    anything unexpected. Confirm the exact endpoint/shape against a live account
    (the design must be a URL Gelato can fetch - i.e. print-file hosting set up)."""
    import requests
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    try:
        resp = requests.post(
            f"{_PRODUCT_API}/mockups",
            headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
            json={"productUid": product_uid,
                  "files": [{"type": "default", "url": design_url}]},
            timeout=45)
        if resp.status_code not in (200, 201):
            return None
        return _extract_image_url(resp.json())
    except Exception:  # noqa: BLE001 — any failure -> fall back to the flat artwork
        return None


def design_mockup_for_order(order: dict, design_path: str = None) -> str | None:
    """Real product mockup of the BUYER'S design on the ordered garment, for the
    customer proof.

    GUARDRAILS: key-gated + TEST_MODE-safe + ADDITIVE. Returns None (so the proof
    falls back to the flat artwork) in TEST_MODE, without a key, for a non-apparel
    order, with no resolvable garment UID, or on any failure. It is purely a visual
    aid in the proof - it does NOT change the print file and cannot bypass the
    customer's proof approval (the parity-gate hash still fingerprints the real
    artwork). Never raises.
    """
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        if TEST_MODE or not GELATO_API_KEY or not isinstance(order, dict):
            return None
        if order.get("product_type") != "apparel":
            return None
        uid = order.get("gelato_product_uid")
        if not uid:
            from quoteforge.etsy.apparel_catalog import resolve_apparel_uid
            uid = resolve_apparel_uid(order.get("gelato_sku"))
        design = design_path or order.get("artwork_url") or ""
        # Gelato must be able to FETCH the design - a local path can't be mocked up.
        if not uid or not str(design).lower().startswith(("http://", "https://")):
            return None
        return _gelato_create_design_mockup(uid, design)
    except Exception:  # noqa: BLE001
        return None
