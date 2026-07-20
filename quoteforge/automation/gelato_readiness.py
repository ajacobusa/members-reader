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
        # The MANUAL/owner map is the trusted path -> status 'verified' AND approved for
        # go-live on write (an owner who types a real UID has vouched for it). The AUTO
        # resolver uses draft_uid() instead, which leaves approved_for_go_live=0.
        conn.execute("""
            INSERT INTO gelato_uid_registry (sku, product_family, product_uid, source,
                status, match_score, match_reason, approved_for_go_live, verified_at, updated_at)
            VALUES (?,?,?,?, 'verified', 1.0, 'manual owner map', 1,
                    datetime('now'), datetime('now'))
            ON CONFLICT(sku) DO UPDATE SET
              product_family=excluded.product_family, product_uid=excluded.product_uid,
              source=excluded.source, status='verified', match_score=1.0,
              match_reason='manual owner map', approved_for_go_live=1,
              verified_at=datetime('now'), updated_at=datetime('now')
        """, (sku, fam, str(product_uid).strip(), source or ""))
        row = conn.execute("SELECT * FROM gelato_uid_registry WHERE sku=?", (sku,)).fetchone()
    return dict(row)


def draft_uid(product_family: str, sku: str, product_uid: str, *, score: float,
              reason: str = "", source: str = "resolver") -> dict:
    """Record an AUTO-resolved UID as a DRAFT (never go-live). status is 'draft' for a
    high-confidence match (>=0.95) or 'needs_review' below - and approved_for_go_live stays
    0 either way, so a draft can NEVER reach the runtime map until an admin approves it.
    Refuses a GEL-*/empty value and an unknown family (same as the manual path)."""
    fam = (product_family or "").strip().lower()
    if fam not in FAMILIES:
        raise ValueError(f"unknown product_family {product_family!r}")
    sku = (sku or "").strip()
    if not sku:
        raise ValueError("sku is required")
    if _is_placeholder(product_uid):
        raise ValueError(f"invalid productUid {product_uid!r}: placeholder/empty rejected")
    status = "draft" if float(score) >= 0.95 else "needs_review"
    with _conn() as conn:
        conn.execute("""
            INSERT INTO gelato_uid_registry (sku, product_family, product_uid, source,
                status, match_score, match_reason, approved_for_go_live, verified_at, updated_at)
            VALUES (?,?,?,?, ?, ?, ?, 0, datetime('now'), datetime('now'))
            ON CONFLICT(sku) DO UPDATE SET
              product_family=excluded.product_family, product_uid=excluded.product_uid,
              source=excluded.source, status=excluded.status, match_score=excluded.match_score,
              match_reason=excluded.match_reason, approved_for_go_live=0,
              updated_at=datetime('now')
        """, (sku, fam, str(product_uid).strip(), source or "resolver", status,
              float(score), reason or ""))
        row = conn.execute("SELECT * FROM gelato_uid_registry WHERE sku=?", (sku,)).fetchone()
    return dict(row)


def verify_uid(sku: str, *, checker=None) -> dict:
    """Independently VERIFY a drafted UID against the Gelato API (does the productUid exist?)
    before it can be approved. Promotes draft/needs_review -> 'verified' on a positive check;
    leaves it unchanged otherwise. `checker(product_uid)->bool` is injectable / defaults to a
    defensive live Gelato lookup. Never auto-approves - an admin still has to approve."""
    rows = [r for r in registry_rows() if r["sku"] == sku]
    if not rows:
        return {"sku": sku, "verified": False, "reason": "not in registry"}
    row = rows[0]
    ok = False
    try:
        chk = checker or _gelato_uid_exists
        ok = bool(chk(row["product_uid"]))
    except Exception as exc:  # noqa: BLE001 - a check error never verifies
        logger.warning("verify_uid check failed for %s: %s", sku, exc)
        ok = False
    if ok:
        with _conn() as conn:
            conn.execute("UPDATE gelato_uid_registry SET status='verified', "
                         "verified_at=datetime('now'), updated_at=datetime('now') WHERE sku=?",
                         (sku,))
    return {"sku": sku, "verified": ok, "product_uid": row["product_uid"]}


def _gelato_uid_exists(product_uid: str) -> bool:
    """DEFENSIVE live check that a productUid resolves in the Gelato product API. Never
    raises; False without a key / in TEST_MODE / on any unexpected shape."""
    if not _live_enabled() or _is_placeholder(product_uid):
        return False
    try:
        import requests
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        resp = requests.get(f"https://product.gelatoapis.com/v3/products/{product_uid}",
                            headers={"X-API-KEY": GELATO_API_KEY}, timeout=20)
        return resp.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.warning("gelato uid existence check failed (defensive): %s", exc)
        return False


def set_uid_status(sku: str, status: str, *, approved: bool | None = None) -> dict:
    """Admin transition of a registry row's lifecycle (approve/reject). approve sets
    status='approved' + approved_for_go_live=1; reject sets 'blocked' + 0."""
    with _conn() as conn:
        if approved is None:
            conn.execute("UPDATE gelato_uid_registry SET status=?, updated_at=datetime('now') "
                         "WHERE sku=?", (status, sku))
        else:
            conn.execute("UPDATE gelato_uid_registry SET status=?, approved_for_go_live=?, "
                         "updated_at=datetime('now') WHERE sku=?",
                         (status, 1 if approved else 0, sku))
        row = conn.execute("SELECT * FROM gelato_uid_registry WHERE sku=?", (sku,)).fetchone()
    return dict(row) if row else {}


def approve_uid(sku: str) -> dict:
    """Admin approves a VERIFIED draft for go-live (the only thing that lets it export)."""
    return set_uid_status(sku, "approved", approved=True)


def reject_uid(sku: str) -> dict:
    """Admin rejects a mapping -> blocked, never exported."""
    return set_uid_status(sku, "blocked", approved=False)


# ─────────── Auto-approval: exact colour-sibling extension (guardrailed) ───────────
# Owner policy 2026-07-20: a drafted mapping may go live WITHOUT a manual approval
# ONLY when it is a pure COLOUR extension of a pattern the owner already vouched
# for. Guardrails (each fails CLOSED - the draft simply stays in the queue):
#   1. its productUid differs from an OWNER-approved (non-auto) sibling's UID in
#      exactly ONE segment, and that segment is a colour (gco/bco pure-colour keys,
#      or mmat with the material prefix preserved: ceramic-blue may extend
#      ceramic-white, never heat-transfer-black). Size / tier / quality / print-mode
#      changes are NEVER auto-approved.
#   2. its draft reason carries no translation/substitution/visual-judgement marker.
#   3. the UID is 1:1 (no other SKU claims it).
#   4. the UID EXISTS in the live product API right now (injectable checker;
#      no key / TEST_MODE -> check returns False -> stays owner-gated).
# Every auto-approval is stamped source='auto-exact-colour' and re-audited daily by
# infra_check invariant 92 (auto_approved_mappings_guardrailed).

AUTO_APPROVE_SOURCE = "auto-exact-colour"
_PURE_COLOUR_KEYS = {"gco", "bco"}
_MATERIAL_COLOUR_KEYS = {"mmat"}
_AUTO_REASON_BLOCKLIST = ("translat", "substitut", "needs visual", "nearest")


def _colour_sibling_of(uid: str, approved_uid: str) -> bool:
    """True when `uid` differs from `approved_uid` in exactly ONE '_' segment whose
    key is a colour key (material prefix preserved for material+colour keys)."""
    a, b = (uid or "").split("_"), (approved_uid or "").split("_")
    if len(a) != len(b) or len(a) < 4:
        return False
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diffs) != 1 or diffs[0] == 0:
        return False
    i = diffs[0]
    key = a[i - 1]
    if key in _PURE_COLOUR_KEYS:
        return True
    if key in _MATERIAL_COLOUR_KEYS:
        return a[i].rsplit("-", 1)[0] == b[i].rsplit("-", 1)[0]
    return False


def auto_approve_exact_colour_siblings(*, checker=None) -> list[dict]:
    """Apply the guardrailed auto-approval policy to the pending queue. Returns one
    action dict per queue row: {sku, action: 'approved'|'skipped', reason}. Only
    'approved' rows change state; everything else stays for the owner."""
    actions: list[dict] = []
    all_rows = registry_rows()
    owner_approved = [r for r in all_rows
                     if r.get("approved_for_go_live")
                     and (r.get("source") or "") != AUTO_APPROVE_SOURCE]
    uid_owner = {}                              # uid -> sku (1:1 audit over ALL rows)
    for r in all_rows:
        uid_owner.setdefault(r.get("product_uid"), r["sku"])
    chk = checker or _gelato_uid_exists
    for row in pending_review():
        sku, uid = row["sku"], row.get("product_uid") or ""
        reason = (row.get("match_reason") or "").lower()
        if any(t in reason for t in _AUTO_REASON_BLOCKLIST):
            actions.append({"sku": sku, "action": "skipped",
                            "reason": "draft reason needs owner judgement"})
            continue
        sib = next((s for s in owner_approved
                    if s["product_family"] == row["product_family"]
                    and _colour_sibling_of(uid, s.get("product_uid") or "")), None)
        if sib is None:
            actions.append({"sku": sku, "action": "skipped",
                            "reason": "no owner-approved exact colour sibling"})
            continue
        if uid_owner.get(uid, sku) != sku:
            actions.append({"sku": sku, "action": "skipped",
                            "reason": f"uid already claimed by {uid_owner[uid]}"})
            continue
        try:
            exists = bool(chk(uid))
        except Exception as exc:  # noqa: BLE001 - a check error never approves
            logger.warning("auto-approve existence check failed for %s: %s", sku, exc)
            exists = False
        if not exists:
            actions.append({"sku": sku, "action": "skipped",
                            "reason": "live existence check unavailable/negative"})
            continue
        note = (f"{row.get('match_reason') or ''}; AUTO-APPROVED: exact colour "
                f"sibling of {sib['sku']} (colour-only diff, live-verified, 1:1)")
        with _conn() as conn:
            conn.execute(
                "UPDATE gelato_uid_registry SET status='approved', "
                "approved_for_go_live=1, source=?, match_reason=?, "
                "verified_at=datetime('now'), updated_at=datetime('now') WHERE sku=?",
                (AUTO_APPROVE_SOURCE, note, sku))
        actions.append({"sku": sku, "action": "approved",
                        "reason": f"exact colour sibling of {sib['sku']}"})
        logger.info("auto-approved %s (colour sibling of %s)", sku, sib["sku"])
    return actions


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
    """{sku: product_uid} for every APPROVED-FOR-GO-LIVE, non-placeholder registry row.
    This is THE gate: only rows an admin has approved (or the trusted manual map) reach the
    runtime UID map. An auto-resolved draft (approved_for_go_live=0) is excluded until
    approved; a stray GEL-* is defensively excluded."""
    return {r["sku"]: r["product_uid"] for r in registry_rows()
            if r.get("approved_for_go_live") and not _is_placeholder(r["product_uid"])}


def pending_review() -> list[dict]:
    """Registry rows awaiting admin action (drafted/needs_review/verified but not yet
    approved) - the admin approval queue."""
    return [r for r in registry_rows()
            if not r.get("approved_for_go_live")
            and r["status"] in ("draft", "needs_review", "verified")]


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
    Returns {ok, registry_offenders, runtime_offenders, runtime_read_ok}. Never raises.

    runtime_read_ok is False when the runtime map could not be READ (an exception) - the
    caller must treat that as UNVERIFIED, not clean, in live mode (unverifiable != safe).
    A genuinely empty map reads fine (runtime_read_ok True); only a raise flips it False."""
    registry_offenders = [r["sku"] for r in registry_rows() if _is_placeholder(r["product_uid"])]
    runtime_offenders: list[str] = []
    runtime_read_ok = True
    try:
        from quoteforge.automation.gelato_sync import _uid_map
        rt = _uid_map()
        runtime_offenders = [sku for sku, uid in (rt or {}).items()
                             if _is_placeholder(uid)]
        runtime_read_ok = rt is not None
    except Exception as exc:  # noqa: BLE001 - unreadable map -> UNVERIFIED, not clean
        runtime_read_ok = False
        logger.warning("runtime uid map unreadable (treated as UNVERIFIED, not clean): %s", exc)
    return {"ok": not registry_offenders and not runtime_offenders,
            "runtime_read_ok": runtime_read_ok,
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
