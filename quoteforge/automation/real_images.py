"""Real product images - one orchestrator to get GENUINE Gelato product photos onto the
storefront so a customer visualises the real item as they personalise, with no manual input.

This does NOT scrape (brittle, ToS-risky, wrong-variant, branded). It drives the sanctioned
API path already deployed, in one call, and reports coverage + the exact next step:

  1. UID mapping   - gelato_uid_resolver auto-discovers real productUids (Gate 1).
  2. Store product - a Gelato store product is created from a template (Component 2), which
                     makes Gelato generate the real mockup.
  3. Image pull    - ecommerce_images pulls that product's real previewUrl, re-hosts it
                     same-origin (never leaks the supplier URL), and maps it to our SKU, so
                     the storefront swaps its generated tile for the REAL photo (#180).

The customer then sees their live design composited IN-BROWSER onto that real blank product
photo - real-time, no per-change API call. Everything here is a safe no-op until genuinely
live (key + store id); it never fabricates an image.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _live() -> bool:
    """True only when genuinely live (TEST_MODE off + a Gelato key present)."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return (not TEST_MODE) and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


def coverage() -> dict:
    """How many of our SKUs currently resolve a REAL product image vs a generated tile.
    Read-only; never raises."""
    real = 0
    try:
        from quoteforge.automation import ecommerce_images as ecom
        real = len(ecom.images_by_sku() or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("images_by_sku read skipped: %s", exc)
    unmapped = 0
    try:
        from quoteforge.automation.gelato_uid_resolver import resolver_status
        unmapped = int(resolver_status().get("unmapped_candidates", 0))
    except Exception as exc:  # noqa: BLE001
        logger.debug("resolver_status read skipped: %s", exc)
    return {"real_images": real, "unmapped_skus": unmapped}


def bootstrap(*, pull: bool = False) -> dict:
    """Report real-image readiness, and (if pull + live) pull the real images now.

    pull=False is a read-only status. pull=True runs the ecommerce image sync (refresh) when
    live, so any real store product's photo is pulled + re-hosted + mapped in one shot.
    Returns a structured report incl. the exact ordered next steps. Never raises.
    """
    from quoteforge.config import GELATO_STORE_ID
    live = _live()
    cov = coverage()
    pulled = None
    if pull and live and GELATO_STORE_ID:
        try:
            from quoteforge.automation import ecommerce_images as ecom
            pulled = len(ecom.images_by_sku(refresh=True) or {})
        except Exception as exc:  # noqa: BLE001 - a pull failure never crashes the report
            logger.warning("real-image pull failed: %s", exc)
            pulled = f"error: {exc}"

    steps: list[str] = []
    if not live:
        steps.append("Set GELATO_API_KEY and TEST_MODE=false (live mode).")
    if cov["unmapped_skus"]:
        steps.append("admin gelato-resolve dry-run   # review auto-discovered real UIDs")
        steps.append("admin gelato-resolve apply && admin gelato-readiness export")
    if not GELATO_STORE_ID:
        steps.append("Set GELATO_STORE_ID (connect the Gelato ecommerce store).")
    steps.append("admin gelato-live create-product <TEMPLATE_ID> <TITLE>   # first product")
    steps.append("admin real-images pull   # pull the real photo(s) + re-host + map")
    if not steps[:-2]:
        steps = ["Live + mapped: run `admin real-images pull` to refresh real photos."]

    return {"live": live, "store_id_set": bool(GELATO_STORE_ID),
            "real_images": cov["real_images"], "unmapped_skus": cov["unmapped_skus"],
            "pulled": pulled, "next_steps": steps}


def format_report(rep: dict) -> str:
    """Render bootstrap() as a readable report for the CLI."""
    lines = ["=" * 56, "REAL PRODUCT IMAGES", "=" * 56,
             f"live               : {rep['live']}",
             f"store connected    : {rep['store_id_set']}",
             f"real images mapped : {rep['real_images']}",
             f"SKUs needing a UID : {rep['unmapped_skus']}"]
    if rep.get("pulled") is not None:
        lines.append(f"pulled this run    : {rep['pulled']}")
    lines.append("-" * 56)
    lines.append("Next:")
    lines += [f"  {i+1}. {s}" for i, s in enumerate(rep["next_steps"])]
    return "\n".join(lines)
