"""Generate the starter Gelato UID-map file (GELATO_UID_MAP_FILE).

Enumerates every Gelato SKU we reference across ALL product families (wall-art, frames,
apparel, mug, calendar, branded) and writes a JSON map - {placeholder_sku: real_uid} -
with a blank value for each SKU not yet mapped, so the owner just pastes in the real
Gelato productUids for the products they're launching with.

Safe + re-runnable:
  - PRESERVES every real value already in the file/env (no data loss) - run it again
    after `wallart-automap` (which auto-fills wall-art) and it only ADDS blanks.
  - NORMALISES any value still left as a GEL-* placeholder back to blank.
  - composite framed SKUs ('{poster}+{frame}') are skipped - they are not a single
    Gelato productUid (frame + poster are mapped separately).
The daily-qa agent reports how many remain placeholder, giving a live 'X of N mapped'.
"""
from __future__ import annotations


def all_skus() -> set:
    """Every mappable Gelato SKU across all product families + frames (GEL-* only,
    excluding composite framed SKUs)."""
    skus: set = set()

    def _collect(getter):
        """Add each non-composite GEL-* SKU from a build function to the set."""
        try:
            for v in getter():
                s = getattr(v, "gelato_sku", "") or ""
                if s and "+" not in s:
                    skus.add(s)
        except Exception:  # noqa: BLE001 - a missing optional catalog is not fatal
            pass
    from quoteforge.etsy.variations import build_variations
    _collect(build_variations)
    for module, fn in (("apparel_catalog", "build_apparel_variations"),
                       ("mug_catalog", "build_mug_variations"),
                       ("calendar_catalog", "build_calendar_variations"),
                       ("branded_catalog", "build_branded_variations")):
        try:
            m = __import__(f"quoteforge.etsy.{module}", fromlist=[fn])
            _collect(getattr(m, fn))
        except Exception:  # noqa: BLE001
            pass
    try:
        from quoteforge.etsy.frames import all_frames
        for f in all_frames():
            s = getattr(f, "gelato_sku", "") or ""
            if s:
                skus.add(s)
    except Exception:  # noqa: BLE001
        pass
    return {s for s in skus if str(s).upper().startswith("GEL-")}


def build_template(existing: dict | None = None) -> dict:
    """The merged map: every existing entry preserved, a blank added for each known
    SKU not yet present, and any still-placeholder value normalised to blank."""
    out = dict(existing or {})
    for sku in all_skus():
        out.setdefault(sku, "")
    for sku, val in list(out.items()):
        if str(val or "").upper().startswith("GEL-"):
            out[sku] = ""                       # a placeholder value isn't a real mapping
    return out


def write_template(path: str | None = None) -> dict:
    """Write/merge the starter UID map to ``path`` (or GELATO_UID_MAP_FILE, or the
    default config/gelato_uid_map.json). Returns {path, total, mapped, remaining}."""
    import json
    import os
    from pathlib import Path
    from quoteforge.automation.gelato_sync import _uid_map
    out = Path(path or os.getenv("GELATO_UID_MAP_FILE") or "config/gelato_uid_map.json")
    try:
        existing = dict(_uid_map())             # current env + file real mappings
    except Exception:  # noqa: BLE001
        existing = {}
    if out.exists():
        try:
            existing.update(json.loads(out.read_text(encoding="utf-8")) or {})
        except Exception:  # noqa: BLE001
            pass
    tmpl = build_template(existing)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tmpl, indent=2, sort_keys=True), encoding="utf-8")
    mapped = sum(1 for v in tmpl.values() if v)
    return {"path": str(out), "total": len(tmpl), "mapped": mapped,
            "remaining": len(tmpl) - mapped}
