"""Gelato live-seam operations - the defensive, gated bridge to a REAL Gelato/Etsy account.

Components 2-4 of zero-owner-iteration, each a no-op until genuinely live and each
DEFENSIVE about the unverified provider shapes (never raises; returns a blocked/empty
result on anything unexpected - the shape is confirmed + logged on the first live call):

  2. create_first_live_product  - create the first store product from a Gelato template and
     capture the raw create response into gelato_live_probe (idempotent: one probe).
  3. sync_live_image_shapes     - pull the live Gelato product + Etsy listing images back and
     record the detected image shape (Gate 2 confirmed).
  4. submit_calibration_test_order - place ONE real physical apparel test order to drive the
     vision-QA calibration. MONEY-OUT, so it is OFF by default and hard-capped: explicit
     CALIBRATION_TEST_ORDER_ENABLED consent, one open test order per productUid (idempotent),
     cost <= CALIBRATION_TEST_ORDER_MAX_SPEND, and it ALWAYS routes through the same
     idempotent router as a customer order (no back-door create).

Nothing here fabricates a productUid or flips a safety flag. In TEST_MODE / without a key
every function is a safe no-op.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_PRODUCT_API = "https://product.gelatoapis.com/v3"


def _live() -> bool:
    """True only when genuinely live (TEST_MODE off + a Gelato key present)."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return (not TEST_MODE) and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


# ── Component 2: create the first live product from a template ───

def _gelato_create_from_template(store_id: str, template_id: str, title: str,
                                 description: str) -> dict:
    """DEFENSIVE live seam: POST products:create-from-template to the Gelato ecommerce
    store. Never raises; returns {} on anything unexpected. The exact request/response
    shape is the one thing to confirm against a live Gelato account (it is captured raw
    into the probe so the shape is visible on the first real call)."""
    try:
        import requests
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        from quoteforge.config import GELATO_ECOMMERCE_URL
        resp = requests.post(
            f"{GELATO_ECOMMERCE_URL}/v1/stores/{store_id}/products:create-from-template",
            headers={"X-API-KEY": GELATO_API_KEY, "Content-Type": "application/json"},
            json={"templateId": template_id, "title": title, "description": description},
            timeout=30)
        if resp.status_code not in (200, 201):
            logger.warning("create-from-template -> %s", resp.status_code)
            return {}
        return resp.json() if isinstance(resp.json(), dict) else {}
    except Exception as exc:  # noqa: BLE001 - unverified provider shape: never crash
        logger.warning("create-from-template failed (defensive): %s", exc)
        return {}


def create_first_live_product(template_id: str, title: str, *, description: str = "",
                              qf_product_id: str = "", sku: str = "",
                              creator=None) -> dict:
    """Create the first live store product from a Gelato template and record a probe.
    Idempotent: if a probe already exists, returns it without creating again. No-op (returns
    {skipped}) in TEST_MODE / without a store id. `creator` is injectable for testing."""
    from quoteforge.automation.gelato_readiness import latest_probe, record_live_probe
    existing = latest_probe()
    if existing:
        return {"skipped": "probe already exists", "probe_id": existing.get("id"),
                "status": existing.get("status")}
    if creator is None and not _live():
        return {"skipped": "not live (TEST_MODE / no key)"}
    from quoteforge.config import GELATO_STORE_ID
    if not GELATO_STORE_ID:
        return {"skipped": "GELATO_STORE_ID not set"}
    if not template_id:
        return {"skipped": "no templateId (create the template in the Gelato dashboard)"}
    make = creator or (lambda: _gelato_create_from_template(
        GELATO_STORE_ID, template_id, title, description))
    raw = make() or {}
    gelato_product_id = ""
    for k in ("id", "productId", "storeProductId", "productUid"):
        if isinstance(raw.get(k), str) and raw[k]:
            gelato_product_id = raw[k]
            break
    pid = record_live_probe(qf_product_id or title, sku,
                            gelato_store_id=GELATO_STORE_ID,
                            gelato_template_id=template_id,
                            gelato_product_id=gelato_product_id,
                            raw_create_response=raw,
                            status="created" if gelato_product_id else "create_failed")
    return {"probe_id": pid, "gelato_product_id": gelato_product_id,
            "created": bool(gelato_product_id)}


# ── Component 3: sync the live image shape back ──────────────────

def sync_live_image_shapes(*, gelato_fetch=None, etsy_fetch=None) -> dict:
    """Pull the live Gelato product + Etsy listing images for the latest probe and record
    the detected image shape (Gate 2 confirmed). No-op if no probe / not live. Fetchers are
    injectable for testing. Never raises."""
    from quoteforge.automation.gelato_readiness import latest_probe, confirm_image_shape
    probe = latest_probe()
    if not probe:
        return {"skipped": "no probe yet - create the first product first"}
    if gelato_fetch is None and etsy_fetch is None and not _live():
        return {"skipped": "not live (TEST_MODE / no key)"}
    gp = {}
    ei = {}
    try:
        if gelato_fetch is not None:
            gp = gelato_fetch(probe.get("gelato_product_id")) or {}
        else:
            from quoteforge.automation import ecommerce_images as ecom
            from quoteforge.config import GELATO_STORE_ID
            gp = ecom._product_detail(GELATO_STORE_ID, probe.get("gelato_product_id") or "") or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("gelato product fetch failed (defensive): %s", exc)
    try:
        if etsy_fetch is not None:
            ei = etsy_fetch(probe) or {}
        else:
            from quoteforge.automation import etsy_api
            _lid = (gp.get("externalId") or gp.get("etsyListingId") or "")
            ei = etsy_api.official_listing_images(_lid) if _lid else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("etsy image fetch failed (defensive): %s", exc)
    row = confirm_image_shape(probe["id"], raw_gelato_product_response=gp,
                              raw_etsy_image_response=ei)
    return {"probe_id": probe["id"], "detected_image_shape": row.get("detected_image_shape"),
            "status": row.get("status")}


# ── Component 4: spend-capped physical test-print order ──────────

def _test_order_placed_for(product_uid: str) -> bool:
    """True if a calibration test order (or approval) already exists for this productUid -
    the idempotency guard so a re-run never double-orders."""
    from quoteforge.db.database import _conn
    with _conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM apparel_print_calibration WHERE product_uid=? "
            "AND status IN ('pending','test_ordered','approved')", (product_uid,)).fetchone()["n"]
    return int(n) > 0


def submit_calibration_test_order(product_uid: str, recipient: dict, artwork_url: str, *,
                                  est_cost: float = 0.0, router=None) -> dict:
    """Place ONE real physical apparel test order to drive vision-QA calibration. Heavily
    gated (money-out): returns a {blocked: reason} unless every rail holds -
    CALIBRATION_TEST_ORDER_ENABLED consent, genuinely live, a real (non-GEL-*) UID, a known
    cost within CALIBRATION_TEST_ORDER_MAX_SPEND, and no existing test order for this UID.
    ALWAYS routes through the idempotent router (never a back-door create). Records a
    'test_ordered' calibration row on success. `router` is injectable for testing."""
    from quoteforge.config import (CALIBRATION_TEST_ORDER_ENABLED,
                                    CALIBRATION_TEST_ORDER_MAX_SPEND, TEST_MODE)
    product_uid = (product_uid or "").strip()
    if not CALIBRATION_TEST_ORDER_ENABLED:
        return {"blocked": "CALIBRATION_TEST_ORDER_ENABLED is off (one-time owner consent)"}
    if router is None and (TEST_MODE or not _live()):
        return {"blocked": "not live (TEST_MODE / no key)"}
    if not product_uid or product_uid.upper().startswith("GEL-"):
        return {"blocked": "no real productUid (placeholder/empty rejected)"}
    if not (recipient and artwork_url):
        return {"blocked": "missing recipient/artwork for the test order"}
    if est_cost <= 0 or est_cost > float(CALIBRATION_TEST_ORDER_MAX_SPEND):
        return {"blocked": f"est_cost {est_cost} outside cap "
                           f"(0, {CALIBRATION_TEST_ORDER_MAX_SPEND}]"}
    if _test_order_placed_for(product_uid):    # cheap fast-path pre-check
        return {"blocked": "a test order already exists for this productUid (idempotent)"}

    # RESERVE before routing: insert a 'pending' row guarded by the UNIQUE partial index
    # ux_apcal_open_uid, so two concurrent calls can't both reach route_order (closes the
    # TOCTOU gap the router's orders-row dedup does not cover for a synthetic calib order).
    import sqlite3
    from quoteforge.db.database import _conn
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO apparel_print_calibration (product_family, product_uid, status, "
                "approver, notes, created_at) VALUES "
                "('apparel', ?, 'pending', 'auto', ?, datetime('now'))",
                (product_uid, f"est_cost={est_cost}"))
    except sqlite3.IntegrityError:
        return {"blocked": "a test order already exists for this productUid (idempotent)"}

    order = {"order_id": f"calib-{product_uid}", "gelato_product_uid": product_uid,
             "vendor": "gelato", "product_type": "apparel", "faithful_artwork": True,
             "calibration_test": True}
    route = router or _route
    result = route(order, recipient, artwork_url) or {}
    if result.get("status") in ("submitted", "ok", "success", "created"):
        with _conn() as conn:            # PROMOTE the reservation to a placed order
            conn.execute(
                "UPDATE apparel_print_calibration SET status='test_ordered', test_order_ref=? "
                "WHERE product_uid=? AND status='pending'",
                (str(result.get("id") or ""), product_uid))
        return {"ordered": True, "vendor_id": result.get("id"), "route": result}
    with _conn() as conn:                # RELEASE the reservation so a corrected retry can proceed
        conn.execute("DELETE FROM apparel_print_calibration "
                     "WHERE product_uid=? AND status='pending'", (product_uid,))
    return {"ordered": False, "route": result}


def _route(order: dict, recipient: dict, artwork_url: str) -> dict:
    """Default router hop for the test order - the SAME idempotent route_order a customer
    order uses (so a test order can never double-submit or bypass the safety gates)."""
    from quoteforge.fulfillment.router import route_order
    return route_order(order, recipient=recipient, artwork_url=artwork_url)


def status() -> dict:
    """A quick read of live-ops readiness for the daily report / CLI."""
    from quoteforge.automation.gelato_readiness import latest_probe
    from quoteforge.config import (CALIBRATION_TEST_ORDER_ENABLED, GELATO_STORE_ID)
    p = latest_probe()
    return {"live": _live(), "store_id_set": bool(GELATO_STORE_ID),
            "probe": {"id": p["id"], "status": p["status"]} if p else None,
            "test_order_enabled": bool(CALIBRATION_TEST_ORDER_ENABLED)}


# ── Doctor: diagnose (and actively probe) the FIRST LIVE PRODUCT prerequisites ──

def _gelato_get_templates(store_id: str) -> list:
    """DEFENSIVE: list the Gelato store's templates so the doctor can tell the owner whether
    a template exists (the usual blocker). [] on any error / not live / no store id."""
    if not _live() or not store_id:
        return []
    try:
        import requests
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        from quoteforge.config import GELATO_ECOMMERCE_URL
        resp = requests.get(f"{GELATO_ECOMMERCE_URL}/v1/stores/{store_id}/templates",
                            headers={"X-API-KEY": GELATO_API_KEY}, timeout=30)
        if resp.status_code != 200:
            logger.warning("gelato templates list -> %s", resp.status_code)
            return []
        d = resp.json()
        return (d if isinstance(d, list) else d.get("templates") or d.get("data") or [])
    except Exception as exc:  # noqa: BLE001 - unverified provider shape: never crash
        logger.warning("gelato templates list failed (defensive): %s", exc)
        return []


def _default_probe() -> dict:
    """Live connectivity probe used by the doctor: is Gelato's catalog API reachable, is the
    ecommerce store reachable, and does at least one template exist? All defensive."""
    from quoteforge.config import GELATO_STORE_ID
    catalog_ok = False
    try:
        from quoteforge.automation.gelato_api import verify_gelato_auth
        catalog_ok = bool(verify_gelato_auth().get("ok"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalog probe failed: %s", exc)
    store_ok = False
    try:
        from quoteforge.automation import ecommerce_images as _ecom
        store_ok = bool(_ecom.status().get("enabled"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("store probe failed: %s", exc)
    return {"catalog_ok": catalog_ok, "store_ok": store_ok,
            "templates": _gelato_get_templates(GELATO_STORE_ID)}


def first_product_doctor(*, probe=None) -> dict:
    """Diagnose EVERY prerequisite for creating the first live product, and ACTIVELY probe the
    live endpoints so a 'still not alive' state shows exactly where it breaks. Read-only;
    never raises. Returns {ready, checks:[{name, ok, detail, fix}], next_action, easier_path}.
    `probe` is injectable (defaults to real live probes) so it is testable without network."""
    from quoteforge.config import GELATO_STORE_ID
    from quoteforge.automation.gelato_api import GELATO_API_KEY
    checks: list[dict] = []

    def add(name, ok, detail, fix=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "fix": fix})

    live = _live()
    add("gelato_api_key", bool(GELATO_API_KEY),
        "set" if GELATO_API_KEY else "MISSING",
        "" if GELATO_API_KEY else "set GELATO_API_KEY (gelato.com -> Settings -> API)")
    add("live_mode", live,
        "live (TEST_MODE off + key)" if live else "TEST_MODE on / no key",
        "" if live else "set TEST_MODE=false once keys are in")
    add("gelato_store_id", bool(GELATO_STORE_ID),
        "set" if GELATO_STORE_ID else "MISSING",
        "" if GELATO_STORE_ID else "connect your Gelato store to Etsy, set GELATO_STORE_ID")

    # Live probes (only meaningful when live; injected in tests). A crashing probe must not
    # crash the doctor - it degrades to all-unreachable (fail safe to not-ready).
    try:
        pr = probe() if probe is not None else (_default_probe() if live else
                                                {"catalog_ok": None, "store_ok": None, "templates": []})
    except Exception as exc:  # noqa: BLE001 - a probe error is a not-ready signal, not a crash
        logger.warning("first-product probe failed: %s", exc)
        pr = {"catalog_ok": False, "store_ok": False, "templates": []}
    if live or probe is not None:
        add("catalog_reachable", pr.get("catalog_ok"),
            "Gelato catalog API answered" if pr.get("catalog_ok") else "catalog API unreachable",
            "" if pr.get("catalog_ok") else "check GELATO_API_KEY validity (admin verify-keys)")
        add("store_reachable", pr.get("store_ok"),
            "ecommerce store answered" if pr.get("store_ok") else "store API unreachable",
            "" if pr.get("store_ok") else "confirm GELATO_STORE_ID + store connected")
        _tmpls = pr.get("templates") or []
        add("template_exists", bool(_tmpls),
            f"{len(_tmpls)} template(s) found" if _tmpls else "NO template found",
            "" if _tmpls else "build 1 template in the Gelato dashboard (variants+mockups+price)")
    else:
        add("live_probes", True, "skipped (not live) - run again with keys set", "")

    # A real approved UID is what a live order/product actually needs
    uid_ready = False
    try:
        from quoteforge.automation.gelato_readiness import registry_uid_map
        uid_ready = bool(registry_uid_map())
    except Exception as exc:  # noqa: BLE001
        logger.debug("uid readiness read skipped: %s", exc)
    add("approved_uid", uid_ready,
        "at least one approved real UID" if uid_ready else "no approved UID yet",
        "" if uid_ready else "admin gelato-resolve dry-run -> gelato-uid verify/approve")

    failing = [c for c in checks if not c["ok"]]
    next_action = next((c["fix"] for c in failing if c["fix"]), "")
    return {"ready": not failing, "checks": checks, "next_action": next_action,
            "easier_path": "Fastest path: create ONE product in the Gelato dashboard (or via "
                           "Gelato's Etsy connector), then run `admin real-images pull` - no "
                           "template ID or API create call needed from here."}
