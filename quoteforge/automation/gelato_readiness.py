"""Gelato readiness pipeline - the three go-live gates, made auditable + automated.

The order path ALREADY hard-blocks the two money-critical cases (a GEL-* placeholder
never submits: fulfillment/router.py; apparel never auto-prints until
APPAREL_PRINT_CALIBRATED: fulfillment/router.py). This module adds the auditable
LEDGER + unified reporting that turns "are we ready?" into a grounded answer, and the
owner-driven approval flow behind Gate 3 - without introducing a second runtime source
of truth.

  Gate 1  UID mapping   - every sellable SKU resolves a VERIFIED real productUid (no
                          GEL-* placeholder). The gelato_uid_registry table is the audit
                          entry point; map_real_gelato_uid() refuses a GEL-* value, and
                          export_registry_to_uid_map() writes the JSON file that
                          gelato_sync._uid_map() already reads - so the registry FEEDS the
                          single runtime source rather than competing with it.
  Gate 2  live probe    - the first real store product (create-from-template) and its
                          Gelato/Etsy image structure are captured raw into
                          gelato_live_probe, so the image pipeline is confirmed against
                          real payloads. Live-gated: a no-op without a key / in TEST_MODE.
  Gate 3  calibration   - a PHYSICAL apparel test print is approved by the owner and
                          recorded in apparel_print_calibration. The global
                          APPAREL_PRINT_CALIBRATED env flag stays the router's master gate;
                          flipping it is only legitimate once an 'approved' row exists.

Hard rules (mirrored from the spec, enforced here + in the order path):
  1. Never send an order using a GEL-* placeholder.       (router + assert_no_gel_placeholders)
  2. Every product must have a verified Gelato productUid. (registry status='verified')
  3. Mappings are grouped by family.                       (FAMILIES)
  4. First live product is created from a template, then synced back for image shape.
  5. Apparel orders are blocked until APPAREL_PRINT_CALIBRATED=true. (router)
  6. Calibration only flips after a physical test print is owner-approved. (Gate 3 ledger)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from quoteforge.db.database import _conn

logger = logging.getLogger(__name__)

# The product families productUid mappings are grouped by (hard rule #3). Each maps to
# the catalog's own per-family verification (the single source for what is sellable and
# whether it is still a placeholder) so Gate 1 never re-derives a SKU list.
FAMILIES: tuple[str, ...] = ("apparel", "mug", "branded", "calendar", "wall-art")

_FAMILY_VERIFY = {
    "apparel": ("quoteforge.etsy.apparel_catalog", "verify_apparel_mappings"),
    "mug": ("quoteforge.etsy.mug_catalog", "verify_mug_mappings"),
    "branded": ("quoteforge.etsy.branded_catalog", "verify_branded_mappings"),
    "calendar": ("quoteforge.etsy.calendar_catalog", "verify_calendar_mappings"),
    "wall-art": ("quoteforge.etsy.gelato_catalog", "verify_catalog_mappings"),
}


def _is_placeholder(uid: str | None) -> bool:
    """A UID is a placeholder (never orderable) if empty or a GEL-* seed value."""
    u = str(uid or "").strip()
    return (not u) or u.upper().startswith("GEL-")


# ─────────────────────────────── Gate 1: UID registry ───────────────────────────────

def map_real_gelato_uid(product_family: str, sku: str, product_uid: str,
                        source: str = "") -> dict:
    """Record a VERIFIED real productUid for a SKU (hard rules #1/#2/#3).

    Refuses a GEL-* placeholder and an unknown family, so a placeholder can never be
    laundered into 'verified'. Upserts one row per SKU. Returns the stored row.
    """
    fam = (product_family or "").strip().lower()
    if fam not in FAMILIES:
        raise ValueError(f"unknown product_family {product_family!r}; expected one of {FAMILIES}")
    sku = (sku or "").strip()
    if not sku:
        raise ValueError("sku is required")
    if _is_placeholder(product_uid):
        raise ValueError(f"invalid productUid {product_uid!r}: placeholder/empty rejected")
    with _conn() as conn:
        conn.execute("""
            INSERT INTO gelato_uid_registry (sku, product_family, product_uid, source,
                                             status, verified_at, updated_at)
            VALUES (?,?,?,?, 'verified', datetime('now'), datetime('now'))
            ON CONFLICT(sku) DO UPDATE SET
              product_family=excluded.product_family, product_uid=excluded.product_uid,
              source=excluded.source, status='verified',
              verified_at=datetime('now'), updated_at=datetime('now')
        """, (sku, fam, str(product_uid).strip(), source or ""))
        row = conn.execute("SELECT * FROM gelato_uid_registry WHERE sku=?", (sku,)).fetchone()
    return dict(row)


def registry_rows(product_family: str | None = None) -> list[dict]:
    """All registry rows, optionally filtered to one family (newest first)."""
    with _conn() as conn:
        if product_family:
            rows = conn.execute(
                "SELECT * FROM gelato_uid_registry WHERE product_family=? ORDER BY sku",
                ((product_family or "").strip().lower(),)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM gelato_uid_registry ORDER BY product_family, sku").fetchall()
    return [dict(r) for r in rows]


def registry_uid_map() -> dict:
    """{sku: product_uid} for every VERIFIED, non-placeholder registry row. A stray
    GEL-* (should be impossible via map_real_gelato_uid) is defensively excluded."""
    return {r["sku"]: r["product_uid"] for r in registry_rows()
            if r["status"] == "verified" and not _is_placeholder(r["product_uid"])}


def _uid_map_path() -> Path:
    """The JSON file gelato_sync._uid_map() reads (GELATO_UID_MAP_FILE or default)."""
    return Path(os.getenv("GELATO_UID_MAP_FILE") or "config/gelato_uid_map.json")


def export_registry_to_uid_map(path: str | os.PathLike | None = None) -> dict:
    """Write the verified registry to the runtime SKU->UID JSON file (single source).

    MERGES over any existing file (a hand-maintained entry is preserved unless the
    registry overrides that SKU). Returns {path, written, total}.
    """
    out = Path(path) if path else _uid_map_path()
    existing: dict = {}
    try:
        existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    except Exception as exc:  # noqa: BLE001 - a corrupt file is replaced, not trusted
        logger.warning("uid map file unreadable, rewriting from registry: %s", exc)
        existing = {}
    merged = {**existing, **registry_uid_map()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
    return {"path": str(out), "written": len(registry_uid_map()), "total": len(merged)}


def gate1_status() -> dict:
    """Per-family UID-mapping readiness, aggregated from each catalog's own verifier
    (the single source for sellable-SKU + placeholder state). ready == no family has a
    placeholder left AND every family reports all_real."""
    import importlib
    families: dict[str, dict] = {}
    ready = True
    for fam, (mod_name, fn) in _FAMILY_VERIFY.items():
        try:
            mod = importlib.import_module(mod_name)
            v = getattr(mod, fn)()
            placeholders = int(v.get("placeholder_count", len(v.get("placeholders", []))))
            total = int(v.get("total", 0))
            configured = int(v.get("configured", total - placeholders))
            fam_ready = placeholders == 0 and total > 0 and configured >= total
            families[fam] = {"total": total, "configured": configured,
                             "placeholders": placeholders, "ready": fam_ready}
            ready = ready and fam_ready
        except Exception as exc:  # noqa: BLE001 - a broken verifier fails the gate closed
            families[fam] = {"error": str(exc), "ready": False}
            ready = False
    reg = registry_rows()
    reg_bad = [r["sku"] for r in reg if _is_placeholder(r["product_uid"])]
    return {"ready": ready and not reg_bad, "families": families,
            "registry_rows": len(reg), "registry_placeholders": reg_bad}


def validate_no_gel_placeholders() -> dict:
    """Grounded Gate-1 assertion input (hard rule #1). Scans BOTH the registry ledger
    and the runtime SKU->UID map (gelato_sync._uid_map) for any GEL-* / empty value.
    Returns {ok, registry_offenders, runtime_offenders}. Never raises."""
    registry_offenders = [r["sku"] for r in registry_rows() if _is_placeholder(r["product_uid"])]
    runtime_offenders: list[str] = []
    try:
        from quoteforge.automation.gelato_sync import _uid_map
        runtime_offenders = [sku for sku, uid in (_uid_map() or {}).items()
                             if _is_placeholder(uid)]
    except Exception as exc:  # noqa: BLE001 - map unreadable -> report, don't crash
        logger.debug("runtime uid map scan skipped: %s", exc)
    return {"ok": not registry_offenders and not runtime_offenders,
            "registry_offenders": sorted(registry_offenders),
            "runtime_offenders": sorted(runtime_offenders)}


def assert_no_gel_placeholders() -> None:
    """Raise if any GEL-* placeholder is present in the registry or runtime map. Used by
    the CI/preflight go-live gate so a placeholder can never reach production."""
    r = validate_no_gel_placeholders()
    if not r["ok"]:
        raise RuntimeError(
            f"Blocked: GEL-* placeholder(s) still present - registry={r['registry_offenders'][:5]} "
            f"runtime={r['runtime_offenders'][:5]}")


# ─────────────────────────────── Gate 2: live probe ─────────────────────────────────

def infer_image_shape(payload) -> str:
    """Best-effort description of an image-response shape, so a future provider change
    that alters the structure is visible in the probe ledger. Never raises."""
    try:
        if isinstance(payload, dict):
            for k in ("images", "mockups", "results", "data"):
                v = payload.get(k)
                if isinstance(v, list) and v:
                    first = v[0]
                    if isinstance(first, str):
                        return f"{k}:list[str]"
                    if isinstance(first, dict):
                        return f"{k}:list[dict:{'|'.join(sorted(first)[:4])}]"
            if "previewUrl" in payload:
                return "previewUrl:str"
            return f"dict:{'|'.join(sorted(payload)[:5])}"
        if isinstance(payload, list) and payload:
            return f"list[{type(payload[0]).__name__}]"
    except Exception as exc:  # noqa: BLE001
        logger.debug("infer_image_shape failed: %s", exc)
    return "unknown"


def record_live_probe(qf_product_id: str, sku: str = "", *, gelato_store_id: str = "",
                      gelato_template_id: str = "", gelato_product_id: str = "",
                      raw_create_response=None, status: str = "created") -> int:
    """Persist a Gate-2 probe row (the create-from-template capture). Returns its id."""
    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO gelato_live_probe (qf_product_id, sku, gelato_store_id,
                gelato_template_id, gelato_product_id, status, raw_create_response,
                created_at, updated_at)
            VALUES (?,?,?,?,?,?,?, datetime('now'), datetime('now'))
        """, (qf_product_id, sku, gelato_store_id, gelato_template_id, gelato_product_id,
              status, json.dumps(raw_create_response) if raw_create_response is not None else None))
        return int(cur.lastrowid)


def confirm_image_shape(probe_id: int, *, raw_gelato_product_response=None,
                        raw_etsy_image_response=None) -> dict:
    """Attach the live Gelato product + Etsy image payloads to a probe and record the
    detected image shape (status -> image_shape_confirmed). Returns the updated row."""
    shape = infer_image_shape(raw_etsy_image_response if raw_etsy_image_response is not None
                              else raw_gelato_product_response)
    with _conn() as conn:
        conn.execute("""
            UPDATE gelato_live_probe SET raw_gelato_product_response=?,
                raw_etsy_image_response=?, detected_image_shape=?,
                status='image_shape_confirmed', updated_at=datetime('now')
            WHERE id=?
        """, (json.dumps(raw_gelato_product_response) if raw_gelato_product_response is not None else None,
              json.dumps(raw_etsy_image_response) if raw_etsy_image_response is not None else None,
              shape, probe_id))
        row = conn.execute("SELECT * FROM gelato_live_probe WHERE id=?", (probe_id,)).fetchone()
    return dict(row) if row else {}


def latest_probe() -> dict | None:
    """The most recent probe row, or None if no live probe has been captured yet."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM gelato_live_probe ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def gate2_status() -> dict:
    """Live-probe readiness: ready once a probe has confirmed the real image shape."""
    p = latest_probe()
    ready = bool(p and p.get("status") == "image_shape_confirmed"
                 and p.get("detected_image_shape") not in (None, "", "unknown"))
    return {"ready": ready,
            "probe": {k: p[k] for k in ("id", "status", "gelato_product_id",
                                        "detected_image_shape")} if p else None}


def _live_enabled() -> bool:
    """True only when genuinely live: not TEST_MODE and a Gelato key present."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return (not TEST_MODE) and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


# ─────────────────────────────── Gate 3: calibration ────────────────────────────────

def record_calibration_approval(product_uid: str, approver: str, *, notes: str = "",
                                product_family: str = "apparel",
                                test_order_ref: str = "") -> dict:
    """Record an owner sign-off that a PHYSICAL test print was reviewed + approved
    (hard rule #6). This does NOT flip APPAREL_PRINT_CALIBRATED - it is the auditable
    evidence that makes flipping it legitimate. Returns the stored row."""
    product_uid = (product_uid or "").strip()
    approver = (approver or "").strip()
    if not product_uid:
        raise ValueError("product_uid (the test-printed variant) is required")
    if not approver:
        raise ValueError("approver (owner id) is required - calibration is owner-only")
    if _is_placeholder(product_uid):
        raise ValueError(f"cannot calibrate a placeholder productUid {product_uid!r}")
    with _conn() as conn:
        cur = conn.execute("""
            INSERT INTO apparel_print_calibration (product_family, product_uid, status,
                approver, notes, test_order_ref, approved_at, created_at)
            VALUES (?,?, 'approved', ?,?,?, datetime('now'), datetime('now'))
        """, (product_family.strip().lower(), product_uid, approver, notes, test_order_ref))
        row = conn.execute("SELECT * FROM apparel_print_calibration WHERE id=?",
                           (cur.lastrowid,)).fetchone()
    return dict(row)


def calibration_approved(product_family: str = "apparel") -> bool:
    """True once at least one PHYSICAL test print has been owner-approved for a family."""
    with _conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM apparel_print_calibration WHERE product_family=? "
            "AND status='approved'", (product_family.strip().lower(),)).fetchone()["n"]
    return int(n) > 0


def gate3_status() -> dict:
    """Calibration readiness. ready == the router's master flag is on AND an owner
    approval row backs it (so the flag was flipped legitimately, hard rule #6). Also
    surfaces the illegitimate state where the flag is on with NO approval on record."""
    from quoteforge.config import APPAREL_PRINT_CALIBRATED
    approved = calibration_approved("apparel")
    flag = bool(APPAREL_PRINT_CALIBRATED)
    return {"ready": flag and approved, "flag": flag, "owner_approved": approved,
            "flag_without_approval": flag and not approved}


# ─────────────────────────────── Unified report ─────────────────────────────────────

def readiness_report() -> dict:
    """The three-gate go-live readiness, grounded. overall_ready is True only when all
    three gates pass. Safe to call anytime (read-only, never raises)."""
    g1, g2, g3 = gate1_status(), gate2_status(), gate3_status()
    return {"gate1_uid_mapping": g1, "gate2_live_probe": g2,
            "gate3_calibration": g3,
            "overall_ready": bool(g1["ready"] and g2["ready"] and g3["ready"]),
            "live_enabled": _live_enabled()}
