"""Go-live Gelato mapping readiness.

Aggregates EVERY department's own Gelato placeholder guard (verify_*_mappings)
into one GO/NO-GO, lists exactly which product families are still unmapped, and
emits a ready-to-paste GELATO_PRODUCT_FAMILY_FILE template. Pure / read-only and
TEST_MODE-safe: it never calls Gelato and never mutates anything, so it is safe
to run any time. The preflight go-live gate consumes `mapping_readiness()`.
"""
from __future__ import annotations

import importlib
import json

# (display name, module, verify-fn). Each verify fn returns
# {total, configured, placeholder_count, placeholders, all_real}.
_DEPARTMENTS = [
    ("Wall Art / Print", "quoteforge.etsy.gelato_catalog", "verify_catalog_mappings"),
    ("Apparel", "quoteforge.etsy.apparel_catalog", "verify_apparel_mappings"),
    ("Branded Products", "quoteforge.etsy.branded_catalog", "verify_branded_mappings"),
    ("Custom Mugs", "quoteforge.etsy.mug_catalog", "verify_mug_mappings"),
    ("Custom Calendars", "quoteforge.etsy.calendar_catalog", "verify_calendar_mappings"),
]

# (module, catalog constant, id attribute) for the family-mappable departments -
# the ones whose products resolve through GELATO_PRODUCT_FAMILY_MAP family keys.
_FAMILY_SOURCES = [
    ("quoteforge.etsy.apparel_catalog", "APPAREL_CATALOG", "garment_id"),
    ("quoteforge.etsy.branded_catalog", "BRANDED_CATALOG", "product_id"),
    ("quoteforge.etsy.mug_catalog", "MUG_CATALOG", "product_id"),
    ("quoteforge.etsy.calendar_catalog", "CALENDAR_CATALOG", "product_id"),
]

_TEMPLATE_VALUE = "REPLACE_WITH_GELATO_PRODUCT_UID"


def mapping_readiness() -> dict:
    """Per-department mapping coverage + an overall GO/NO-GO. Each department's
    own verify_*_mappings is the source of truth; a department that fails to
    import is reported as not-ready rather than crashing the report."""
    depts: list[dict] = []
    for label, mod_name, fn in _DEPARTMENTS:
        try:
            rep = getattr(importlib.import_module(mod_name), fn)()
        except Exception as exc:  # noqa: BLE001
            rep = {"total": 0, "configured": 0, "placeholders": [],
                   "all_real": False, "error": str(exc)}
        depts.append({
            "name": label,
            "total": int(rep.get("total", 0)),
            "configured": int(rep.get("configured", 0)),
            "placeholder_count": int(rep.get("placeholder_count",
                                              len(rep.get("placeholders", [])))),
            "all_real": bool(rep.get("all_real")),
        })
    return {
        "departments": depts,
        "total": sum(d["total"] for d in depts),
        "configured": sum(d["configured"] for d in depts),
        "placeholder_count": sum(d["placeholder_count"] for d in depts),
        "overall_ready": all(d["all_real"] for d in depts) and bool(depts),
    }


def unmapped_families() -> dict:
    """Every distinct product family (across apparel/branded/mug/calendar) that is
    NOT yet mapped to a real Gelato product, plus a ready-to-paste JSON template
    for GELATO_PRODUCT_FAMILY_FILE. Mapping these ~few dozen family keys covers
    all per-colour/size variants."""
    from quoteforge.automation.gelato_variant_resolver import family_key, family_covered
    keys: dict[str, bool] = {}
    for mod_name, cat_name, id_attr in _FAMILY_SOURCES:
        try:
            catalog = getattr(importlib.import_module(mod_name), cat_name)
        except Exception:  # noqa: BLE001
            continue
        for product in catalog:
            pid = getattr(product, id_attr, None)
            if not pid or family_covered(pid):
                continue
            fk = family_key(pid)
            if fk:
                keys[fk] = True
    families = sorted(keys)
    return {
        "unmapped_families": families,
        "count": len(families),
        "template": {fk: _TEMPLATE_VALUE for fk in families},
    }


def format_readiness_text() -> str:
    """A plain-text go-live readiness dashboard for the admin CLI."""
    r = mapping_readiness()
    lines = ["=" * 60, "GO-LIVE READINESS - Gelato product mappings", "=" * 60]
    for d in r["departments"]:
        icon = "[ OK ]" if d["all_real"] else "[MAP ]"
        lines.append(f"  {icon} {d['name']:<20} "
                     f"{d['configured']}/{d['total']} mapped"
                     + ("" if d["all_real"] else f"  ({d['placeholder_count']} to map)"))
    lines.append("-" * 60)
    if r["overall_ready"]:
        lines.append("  RESULT: READY - every department is mapped to a real Gelato product.")
    else:
        u = unmapped_families()
        lines.append(f"  RESULT: NOT READY - {r['placeholder_count']} variant(s) across "
                     f"{u['count']} product families still need a real Gelato UID.")
        lines.append("  Run `python -m quoteforge.admin map-gelato` for the fill-in template.")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_map_template_text() -> str:
    """The actionable mapping helper: the list of unmapped families + a JSON
    template the owner pastes into their GELATO_PRODUCT_FAMILY_FILE (one real
    Gelato product UID per family)."""
    u = unmapped_families()
    if not u["count"]:
        return "All product families are already mapped to real Gelato products."
    lines = [
        f"{u['count']} product families still need a real Gelato product UID.",
        "Find each product in your Gelato dashboard, copy its product UID, and",
        "paste it below into your GELATO_PRODUCT_FAMILY_FILE (JSON). Then re-run",
        "`python -m quoteforge.admin go-live-readiness`.", "",
        json.dumps(u["template"], indent=2, sort_keys=True),
    ]
    # The Wall Art / Print catalog resolves through its own GELATO_UID_MAP (not
    # the family map), so point the owner at the existing sync command for it.
    print_dept = next((d for d in mapping_readiness()["departments"]
                       if d["name"].startswith("Wall Art") and not d["all_real"]), None)
    if print_dept:
        lines += ["", "Note: the Wall Art / Print catalog maps separately via its own "
                  "GELATO_UID_MAP - run `python -m quoteforge.admin gelato-sync` for that."]
    return "\n".join(lines)
