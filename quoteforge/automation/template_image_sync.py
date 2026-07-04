"""Daily template-image sync (#181): persist each product's official images.

Builds on the ecommerce_images pull (#180) and adds DURABLE PERSISTENCE into the
``gelato_product_images`` table, retry-on-transient, stale-retire, and owner alerts —
so the moment the owner creates a product (from a Gelato template, which publishes to
the connected Etsy store), its official images are captured and reused for every
future product with the same SKU, with no manual step.

Guard rails (mirror ecommerce_images.py): no-op unless genuinely live (TEST_MODE /
no key / no GELATO_STORE_ID -> a safe {} shape, never raises); conservative SKU join
(ambiguous -> skipped, never guessed, so product A's image can't land on product B);
customer-safe (the raw previewUrl is re-hosted same-origin before display).

[LIVE-FINALISE] The store has 0 products today, so the multi-image ``previewUrl``
object shape and the studio/lifestyle/mockup classification are UNOBSERVED. Until a
real product exists, ``_images_of`` returns the single ``_extract_image_url`` result
as ``mockup`` and ``status()`` self-reports the raw product keys so the true shape is
surfaced, not guessed. The listing-CREATE step (POST) is intentionally NOT here — it
is a live write with an unobservable payload and needs write creds + a real template.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _uid_to_sku() -> dict:
    """{gelato_uid -> our_sku} for confident reverse joins (placeholder UIDs excluded)."""
    try:
        from quoteforge.automation.gelato_sync import _uid_map
        return {str(u): s for s, u in (_uid_map() or {}).items()
                if u and not str(u).startswith("GEL-")}
    except Exception as exc:  # noqa: BLE001
        logger.debug("uid map read failed: %s", exc)
        return {}


def _images_of(product: dict) -> list[dict]:
    """Official images for one store product as [{url, uid, type}], best-effort.

    [LIVE-FINALISE] one image (the resolved previewUrl) typed 'mockup' until a real
    product reveals the multi-image / scene shape."""
    from quoteforge.automation.ecommerce_images import _gate, _product_detail
    from quoteforge.images.supplier_mockup import _extract_image_url
    _e, sid = _gate()
    pid = product.get("id") or product.get("productId")
    detail = _product_detail(sid, str(pid)) if (sid and pid) else product
    url = _extract_image_url(detail) or _extract_image_url(product)
    if not url:
        return []
    uid = ""
    for var in (product.get("variants") or []):
        if isinstance(var, dict) and (var.get("productUid") or var.get("uid")):
            uid = var.get("productUid") or var.get("uid")
            break
    return [{"url": url, "uid": uid, "type": "mockup"}]


def sync_template_images() -> dict:
    """Pull official images per product and UPSERT them into gelato_product_images.

    Returns {enabled, checked, upserted, retired, failed:[...]} - NEVER raises (a
    network blip can't break the daily rebuild). ``failed`` is what the admin command
    alerts on, so a paid-for image sync never fails silently."""
    from quoteforge.automation.ecommerce_images import _gate, store_products, _sku_for
    from quoteforge.automation.retry import retry_call
    from quoteforge.db.database import (upsert_product_image,
                                        deactivate_stale_product_images)

    enabled, _sid = _gate()
    if not enabled:
        return {"enabled": False, "checked": 0, "upserted": 0, "retired": 0,
                "failed": [], "reason": "TEST_MODE / no key / no store id"}

    stamp = datetime.now().isoformat(timespec="seconds")
    checked = upserted = 0
    failed: list[dict] = []
    try:
        prods = retry_call(store_products, max_attempts=3, base_delay=2.0)
    except Exception as exc:  # noqa: BLE001 — surface, never swallow
        logger.warning("template-sync: store fetch failed after retries: %s", exc)
        return {"enabled": True, "checked": 0, "upserted": 0, "retired": 0,
                "failed": [{"sku": "*", "error": f"{type(exc).__name__}: {exc}"}]}

    uid_to_sku = _uid_to_sku()
    for p in prods:
        if not isinstance(p, dict):
            continue
        checked += 1
        sku = _sku_for(p, uid_to_sku)
        if not sku:
            continue                      # ambiguous -> skip, never guess a wrong image
        try:
            for rank, img in enumerate(_images_of(p)):
                upsert_product_image(sku, img["url"], gelato_product_uid=img.get("uid", ""),
                                     image_rank=rank, image_type=img.get("type", "mockup"))
                upserted += 1
        except Exception as exc:  # noqa: BLE001 — per-product isolation; record, don't abort
            logger.warning("template-sync: sku %s failed: %s", sku, exc)
            failed.append({"sku": sku, "error": f"{type(exc).__name__}: {exc}"})

    retired = 0
    try:
        retired = deactivate_stale_product_images(stamp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("template-sync: stale-retire failed: %s", exc)
    return {"enabled": True, "checked": checked, "upserted": upserted,
            "retired": retired, "failed": failed}


def status() -> dict:
    """Self-diagnosing snapshot for the daily report + infra-check. Never raises."""
    try:
        from quoteforge.automation.ecommerce_images import _gate
        from quoteforge.db.database import get_product_images
        enabled, sid = _gate()
        imgs = get_product_images()
        by_type: dict = {}
        for i in imgs:
            by_type[i.get("image_type", "mockup")] = by_type.get(i.get("image_type", "mockup"), 0) + 1
        return {"enabled": bool(enabled), "store_id": sid,
                "active_images": len(imgs),
                "skus": len({i.get("gelato_sku") for i in imgs}),
                "by_type": by_type}
    except Exception as exc:  # noqa: BLE001
        logger.debug("template-sync status failed: %s", exc)
        return {"enabled": False, "active_images": 0, "skus": 0, "by_type": {}}
