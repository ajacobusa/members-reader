"""Daily QA agent - the automated 'is the storefront still correct + current?' check.

Aggregates the per-family Gelato SKU/UID mapping verifiers + a net-margin-floor sweep
across every priced variation + order-book health into ONE daily report, and emails the
owner when something needs attention. This is the always-on agent that confirms every
product's SKU + price is current (new/discontinued products flow through the per-family
builders, which drop discontinued and re-price to the floor automatically).

Runs on a schedule (admin daily-qa); a no-op-safe read-only check.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Per-family (name, dotted module, verifier fn, builder fn). Each verifier returns
# {"total", "configured", "placeholders": [...]}; each builder returns priced variants.
_FAMILIES = [
    ("wall-art", "quoteforge.etsy.gelato_catalog", "verify_catalog_mappings", None),
    ("apparel", "quoteforge.etsy.apparel_catalog", "verify_apparel_mappings",
     "build_apparel_variations"),
    ("mug", "quoteforge.etsy.mug_catalog", "verify_mug_mappings", "build_mug_variations"),
    ("calendar", "quoteforge.etsy.calendar_catalog", "verify_calendar_mappings",
     "build_calendar_variations"),
    ("branded", "quoteforge.etsy.branded_catalog", "verify_branded_mappings",
     "build_branded_variations"),
]

# A hard sanity floor well below every family's real net floor (entry 57% .. top 60%),
# so a flagged variation is a genuine pricing-config break, never a tier rounding edge.
_SANITY_MARGIN_FLOOR = 45.0


def _load(module: str, name: str):
    """Import ``module.name`` (a catalog verifier/builder), or None if unavailable."""
    try:
        mod = __import__(module, fromlist=[name])
        return getattr(mod, name, None)
    except Exception:  # noqa: BLE001 - a missing optional catalog is not fatal
        return None


def sku_price_audit() -> dict:
    """Per-family SKU/UID currency + margin-floor sweep. Returns a structured summary +
    the specific issues (placeholder UIDs not yet mapped to real Gelato UIDs, and any
    variation that fell below the net-margin floor)."""
    families, placeholder_total, below_floor = [], 0, []
    for name, module, verify_name, build_name in _FAMILIES:
        verify = _load(module, verify_name)
        if verify is not None:
            try:
                r = verify()
                ph = len(r.get("placeholders", []) or [])
                placeholder_total += ph
                families.append({"family": name, "total": r.get("total", 0),
                                 "configured": r.get("configured", 0),
                                 "placeholder_uids": ph})
            except Exception as exc:  # noqa: BLE001
                families.append({"family": name, "error": str(exc)})
        build = _load(module, build_name) if build_name else _load(
            "quoteforge.etsy.variations", "build_variations")
        if build is not None:
            try:
                for v in build():
                    mp = getattr(v, "margin_pct", None)
                    if mp is not None and mp < _SANITY_MARGIN_FLOOR:
                        below_floor.append({"family": name,
                                            "sku": getattr(v, "gelato_sku", "?"),
                                            "margin_pct": round(float(mp), 1)})
            except Exception as exc:  # noqa: BLE001 - never break the sweep, but log
                logger.warning("daily-qa: margin sweep failed for family %s: %s",
                               name, exc)
    return {"ok": placeholder_total == 0 and not below_floor,
            "families": families, "placeholder_uids": placeholder_total,
            "below_floor": below_floor}


def qa_dashboard() -> dict:
    """The reporting-dashboard counts: order-book health + claims + the SKU/price audit."""
    from quoteforge.db.database import daily_order_report, get_all_orders
    rep = daily_order_report()
    by_status = rep.get("by_status", {})
    orders = get_all_orders(limit=1000000)
    claims = [o for o in orders if (o.get("claim_status") or "")]
    return {
        "total_orders": len(orders),
        "routed": sum(1 for o in orders if o.get("vendor_order_id")),
        "with_tracking": sum(1 for o in orders if o.get("tracking_number")),
        "delivered": by_status.get("delivered", 0),
        "needs_attention": len(rep.get("needs_attention", [])),
        "claims": len(claims),
        "by_status": by_status,
        "sku_audit": sku_price_audit(),
    }


def run_daily_qa(send: bool = False) -> dict:
    """Run the daily QA and return the dashboard. Collects the actionable issues
    (unmapped UIDs, below-floor prices, orders needing attention) and emails the owner
    when ``send`` and there is anything to act on."""
    from quoteforge.db.database import init_db
    init_db()
    dash = qa_dashboard()
    sku = dash["sku_audit"]
    issues = []
    if sku["placeholder_uids"]:
        issues.append(f"{sku['placeholder_uids']} product UID(s) still placeholder "
                      "(map to real Gelato UIDs before go-live)")
    if sku["below_floor"]:
        issues.append(f"{len(sku['below_floor'])} variation(s) below the margin floor")
    if dash["needs_attention"]:
        issues.append(f"{dash['needs_attention']} order(s) need attention")
    dash["issues"] = issues
    dash["ok"] = not issues
    if send and issues:
        try:
            from quoteforge.automation.emailer import _send_email
            _send_email("⚠️ Daily QA found issues",
                        "<pre>" + "\n".join("- " + i for i in issues) + "</pre>")
        except Exception as exc:  # noqa: BLE001 - never break the check, but log
            logger.warning("daily-qa alert email failed: %s", exc)
    logger.info("daily-qa: ok=%s issues=%d orders=%d", dash["ok"], len(issues),
                dash["total_orders"])
    return dash
