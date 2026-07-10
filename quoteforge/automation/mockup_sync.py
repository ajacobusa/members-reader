"""Gelato mockup sync — the daily, all-local engine behind the spec
(specs/2026-06-24-gelato-mockup-sync-design.md).

Keeps every product's storefront preview matching the real Gelato product via a
per-product state machine, where each step is a CHECKPOINT recorded in
``config/mockups.json`` and **nothing publishes without the two confirming agents
agreeing** (gelato-mockup-reviewer PASS && gelato-sku-image-match MATCH).

Guard rails (non-negotiable, enforced here):
  * **No-op until genuinely live.** Every Gelato call short-circuits in TEST_MODE,
    without an API key, or for a placeholder ``GEL-*`` UID — the generated preview
    shows; nothing errors.
  * **Never publish the unconfirmed.** ``live_mockups()`` (what the storefront
    reads) only ever returns products whose ``confirmed`` is True. A changed Gelato
    image drops the product back to READY and re-queues the agents.
  * **No supplier leak.** Only the re-hosted, same-origin local path reaches the
    build; the Gelato URL lives in an internal checkpoint, never emitted.
  * **Never auto-edit the SKU→UID mapping, never flip TEST_MODE, never order.**
  * **Never break the build.** Any per-product failure keeps that product's last
    good ``live`` block (or the generated fallback) and is reported.

Future growth: products are enumerated generically from the per-family catalogs via
``PRODUCT_FAMILIES`` — adding a new Gelato product line is one entry there (or a new
catalog), not a rewrite of this engine.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Per-category default print geometry on the mockup photo (fractions 0–1), used when
# Gelato template printArea isn't available. cyl=round product → the design wraps.
_GEOMETRY_DEFAULTS: dict[str, dict] = {
    "mug":      {"area": [0.33, 0.34, 0.34, 0.34], "cyl": True,  "span": 1.9},
    "bottle":   {"area": [0.33, 0.34, 0.34, 0.34], "cyl": True,  "span": 1.9},
    "branded":  {"area": [0.28, 0.26, 0.44, 0.50], "cyl": False, "span": 1.9},
    "calendar": {"area": [0.20, 0.16, 0.60, 0.50], "cyl": False, "span": 1.9},
    "apparel":  {"area": [0.30, 0.28, 0.40, 0.40], "cyl": False, "span": 1.9},
}
_DEFAULT_GEOMETRY = {"area": [0.30, 0.30, 0.40, 0.40], "cyl": False, "span": 1.9}


# ── Generic product enumeration (future-growth seam) ──────────────────────────

def _pick_mapped_sku(candidates: Iterable[str], fallback: str) -> str:
    """The representative SKU for a product: the FIRST candidate that resolves to a real
    (non-placeholder) UID in the runtime map, else ``fallback``. Fixes the end-to-end
    audit gap 3a: sizes[0]/colors[0] is typically XS/White, which is UNMAPPED for most
    apparel even when 50+ other variants of the same garment ARE mapped - so the sync
    and readiness() under-reported almost every product as 'no real UID'."""
    try:
        from quoteforge.automation.gelato_sync import _uid_map
        m = _uid_map() or {}
    except Exception:  # noqa: BLE001 - unreadable map -> keep the legacy fallback
        return fallback
    for sku in candidates:
        uid = m.get(sku)
        if sku and uid and not str(uid).upper().startswith("GEL-"):
            return sku
    return fallback


def _product_family_loaders() -> list[Callable[[], list[dict]]]:
    """One loader per product line. Each returns a list of
    ``{product_id, name, category, sku, width_px, height_px}``. A new Gelato line =
    a new loader appended here; the rest of the engine is family-agnostic. The
    representative sku prefers a MAPPED variant (see _pick_mapped_sku)."""
    def _mug() -> list[dict]:
        """Mug catalog → product dicts (bottles/tumblers split to category 'bottle')."""
        from quoteforge.etsy.mug_catalog import MUG_CATALOG, _variant_sku
        out = []
        for p in MUG_CATALOG:
            if p.sizes and p.colors:
                sku = _pick_mapped_sku(
                    (_variant_sku(p, s, c) for s in p.sizes for c in p.colors),
                    _variant_sku(p, p.sizes[0], p.colors[0]))
            else:
                sku = p.sku_prefix
            cat = "bottle" if any(k in p.name.lower() for k in ("bottle", "tumbler")) else "mug"
            out.append(dict(product_id=p.product_id, name=p.name, category=cat,
                            sku=sku, width_px=p.width_px, height_px=p.height_px))
        return out

    def _branded() -> list[dict]:
        """Branded catalog → product dicts (bottles/tumblers split to 'bottle')."""
        from quoteforge.etsy.branded_catalog import BRANDED_CATALOG, _variant_sku
        out = []
        for p in BRANDED_CATALOG:
            if getattr(p, "sizes", None) and getattr(p, "colors", None):
                sku = _pick_mapped_sku(
                    (_variant_sku(p, s, c) for s in p.sizes for c in p.colors),
                    _variant_sku(p, p.sizes[0], p.colors[0]))
            else:
                sku = getattr(p, "sku_prefix", p.product_id)
            n = p.name.lower()
            cat = "bottle" if any(k in n for k in ("bottle", "tumbler")) else "branded"
            out.append(dict(product_id=p.product_id, name=p.name, category=cat,
                            sku=sku, width_px=p.width_px, height_px=p.height_px))
        return out

    def _calendar() -> list[dict]:
        """Calendar catalog → product dicts (category 'calendar')."""
        from quoteforge.etsy.calendar_catalog import CALENDAR_CATALOG
        return [dict(product_id=p.product_id, name=p.name, category="calendar",
                     sku=getattr(p, "sku_prefix", p.product_id),
                     width_px=p.width_px, height_px=p.height_px)
                for p in CALENDAR_CATALOG]

    def _apparel() -> list[dict]:
        """Apparel catalog → product dicts keyed by garment_id (category 'apparel')."""
        from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG, apparel_sku_for
        out = []
        for g in APPAREL_CATALOG:
            if g.sizes and g.colors:
                sku = _pick_mapped_sku(
                    (apparel_sku_for(g.garment_id, s, c) or ""
                     for s in g.sizes for c in g.colors),
                    apparel_sku_for(g.garment_id, g.sizes[0], g.colors[0]) or g.garment_id)
            else:
                sku = g.garment_id
            out.append(dict(product_id=g.garment_id, name=g.name, category="apparel",
                            sku=sku or g.garment_id,
                            width_px=getattr(g, "width_px", 0),
                            height_px=getattr(g, "height_px", 0)))
        return out

    return [_mug, _branded, _calendar, _apparel]


def all_products() -> list[dict]:
    """Every sellable product across all families. Never raises on one bad
    family — a broken catalog skips that line, the rest still sync."""
    out: list[dict] = []
    seen: set[str] = set()
    for load in _product_family_loaders():
        try:
            for p in load():
                pid = p.get("product_id")
                if pid and pid not in seen:
                    seen.add(pid)
                    out.append(p)
        except Exception:  # noqa: BLE001 — one family must never break the sweep
            continue
    return out


# ── config/mockups.json (the local metadata "database") ───────────────────────

def catalog_path() -> Path:
    """Path to the local metadata catalog (``config/mockups.json``; overridable via
    the ``MOCKUP_CATALOG_FILE`` env for tests)."""
    p = os.getenv("MOCKUP_CATALOG_FILE", "").strip()
    if p:
        return Path(p)
    return Path("config") / "mockups.json"


def load_catalog() -> dict:
    """Load the catalog (a safe empty default if missing/unreadable)."""
    try:
        data = json.loads(catalog_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("products"), dict):
            return data
    except Exception as exc:  # noqa: BLE001 - missing/corrupt -> safe empty default
        logger.debug("mockup catalog load failed, using empty default: %s", exc)
    return {"version": SCHEMA_VERSION, "updated_utc": None, "products": {}}


def save_catalog(cat: dict, *, stamp: str | None = None) -> None:
    """Atomic, best-effort write. ``stamp`` is passed in (the build/runtime stamps
    time — this module never calls Date.now()-style nondeterminism itself)."""
    cat["version"] = SCHEMA_VERSION
    if stamp is not None:
        cat["updated_utc"] = stamp
    path = catalog_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cat, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("mockup catalog save failed: %s", exc)


# ── Guard-rail helpers ────────────────────────────────────────────────────────

def _live_gated() -> bool:
    """True when we may talk to Gelato (genuinely live)."""
    try:
        from quoteforge.config import TEST_MODE
        from quoteforge.automation.gelato_api import GELATO_API_KEY
        return (not TEST_MODE) and bool(GELATO_API_KEY)
    except Exception:  # noqa: BLE001
        return False


def _real_uid(sku: str) -> str | None:
    """The genuine Gelato UID for our SKU, or None for unmapped / placeholder."""
    try:
        from quoteforge.automation.gelato_sync import _uid_map
        uid = (_uid_map() or {}).get(sku)
        if not uid or str(uid).startswith("GEL-"):     # placeholder seed
            return None
        return str(uid)
    except Exception:  # noqa: BLE001
        return None


def _geometry_for(category: str) -> dict:
    """Per-category default print geometry (used when no Gelato template placement)."""
    return dict(_GEOMETRY_DEFAULTS.get(category, _DEFAULT_GEOMETRY))


def _ck(ok: bool, at: str | None = None, **extra) -> dict:
    """Build one checkpoint record ``{ok, at, **extra}``."""
    d = {"ok": bool(ok)}
    d.update(extra)
    if at is not None:
        d["at"] = at
    return d


# ── The state machine: sync (checkpoints 1–6) ─────────────────────────────────

def run_sync(*, stamp: str | None = None,
             fetch_image: Callable[[str], str | None] | None = None,
             rehost: Callable[[str, str], tuple[str, str] | None] | None = None,
             printarea: Callable[[str], dict | None] | None = None) -> dict:
    """Run checkpoints 1–6 for every product. Pure of side effects beyond
    ``config/mockups.json`` + the re-host. No-op (no Gelato calls) unless live.

    The Gelato/IO calls are injected so the engine is fully unit-testable:
      * ``fetch_image(uid) -> url|None`` (default: gelato_blank_image)
      * ``rehost(url, product_id) -> (local_src, fingerprint)|None`` (default below)
      * ``printarea(uid) -> {area,cyl,span}|None`` (default: gelato_template_printarea)
    Returns a summary dict.
    """
    cat = load_catalog()
    products = cat.setdefault("products", {})
    summary = {"new": 0, "fetched": 0, "ready": 0, "requeued": 0,
               "skipped": 0, "errors": 0, "live_gated": not _live_gated()}

    if fetch_image is None:
        # #185 audit F2: the default MUST be the provenance dict (url+uid+source),
        # not the bare-URL wrapper - the bare wrapper made the legacy branch rebind
        # EVERY source (override/persisted/ecommerce) to the SKU's real UID "by
        # construction", so confirm()'s wrong-product provenance gate never held
        # anything on the production (admin) path.
        def fetch_image(sku):  # type: ignore
            """Default fetch: the full provenance dict (url+uid+source) for sku."""
            from quoteforge.images import supplier_mockup as _sm
            return _sm.gelato_blank_image_provenance(sku)
    if printarea is None:
        try:
            from quoteforge.images.supplier_mockup import gelato_template_printarea as printarea  # type: ignore
        except Exception:  # noqa: BLE001
            printarea = lambda uid: None  # noqa: E731
    if rehost is None:
        rehost = _default_rehost

    for prod in all_products():
        pid = prod["product_id"]
        rec = products.setdefault(pid, {})
        rec.setdefault("category", prod["category"])
        rec["category"] = prod["category"]
        rec.setdefault("sku", prod["sku"])
        rec["sku"] = prod["sku"]
        rec.setdefault("name", prod["name"])
        rec.setdefault("checkpoints", {})
        rec.setdefault("review", {"verdict": None, "reasons": None, "at": None})
        rec.setdefault("match", {"verdict": None, "reasons": None, "at": None})
        rec.setdefault("confirmed", False)
        rec.setdefault("live", None)
        ck = rec["checkpoints"]
        if "live" not in rec:
            rec["live"] = None
        if rec.get("checkpoints") == {} or not rec.get("status"):
            summary["new"] += 1

        # 1) discovered — needs a real (non-placeholder) Gelato UID
        uid = _real_uid(prod["sku"])
        if not uid:
            ck["discovered"] = _ck(False, stamp, reason="no real UID / placeholder")
            rec["gelato_uid"] = None
            rec["status"] = "skipped"
            summary["skipped"] += 1
            continue
        ck["discovered"] = _ck(True, stamp); rec["gelato_uid"] = uid

        if not _live_gated():
            rec["status"] = rec.get("status") or "discovered"
            continue  # no Gelato calls off-live; keep any existing live block

        # 2) fetched (WITH provenance). The fetch may return a bare url (legacy/test
        #    seam) or a {url, uid, source} dict. resolved_uid is the UID the bytes are
        #    PROVABLY bound to; a bare-url/legacy result is bound to this SKU's resolved
        #    real uid by construction. A None resolved_uid = provenance unverified.
        try:
            res = fetch_image(prod["sku"])
        except Exception:  # noqa: BLE001
            res = None
        if isinstance(res, dict):
            url = res.get("url")
            resolved_uid = res.get("uid")
            src_kind = res.get("source")
        else:
            url = res
            resolved_uid = uid if res else None   # legacy/test: bound to the resolved uid
            src_kind = "legacy"
        if not url:
            ck["fetched"] = _ck(False, stamp, reason="no Gelato image")
            rec["status"] = "error"; summary["errors"] += 1
            continue
        ck["fetched"] = _ck(True, stamp, src=url,
                            resolved_uid=resolved_uid, source=src_kind)
        summary["fetched"] += 1

        # 5) rehosted (download + re-host local, web-opt) — also our change signal
        rh = None
        try:
            rh = rehost(url, pid)
        except Exception:  # noqa: BLE001
            rh = None
        if not rh:
            ck["rehosted"] = _ck(False, stamp, reason="re-host failed")
            rec["status"] = "error"; summary["errors"] += 1
            continue
        local_src, fingerprint = rh

        # 3) validated — sanity guard (bytes present + fingerprint). Deeper
        #    blank-base / type judgement is the reviewer + match agents' job.
        if not fingerprint:
            ck["validated"] = _ck(False, stamp, reason="empty image")
            rec["status"] = "error"; summary["errors"] += 1
            continue
        ck["validated"] = _ck(True, stamp, fingerprint=fingerprint)

        # 4) geometry — Gelato template printArea if available, else type default
        geo = None
        try:
            geo = printarea(uid)
        except Exception:  # noqa: BLE001
            geo = None
        if not (isinstance(geo, dict) and geo.get("area")):
            geo = _geometry_for(prod["category"]); geo_src = "default"
        else:
            geo_src = "template"
        ck["geometry"] = _ck(True, stamp, source=geo_src, **geo)

        # change detection: a NEW/CHANGED image must re-pass the agents
        prev_fp = (rec.get("live") or {}).get("fingerprint")
        if prev_fp and prev_fp != fingerprint:
            rec["confirmed"] = False
            rec["review"] = {"verdict": None, "reasons": None, "at": None}
            rec["match"] = {"verdict": None, "reasons": None, "at": None}
            summary["requeued"] += 1

        # 6) cataloged → READY. The candidate carries resolved_uid so confirm() can
        #    require the image's proven origin UID to equal the SKU's real UID before
        #    it ever publishes (the "right product" data-level guarantee).
        ck["rehosted"] = _ck(True, stamp, path=local_src, fingerprint=fingerprint)
        ck["cataloged"] = _ck(True, stamp)
        rec["candidate"] = {"src": local_src, "fingerprint": fingerprint,
                            "resolved_uid": resolved_uid, **geo}
        rec["status"] = "ready"
        summary["ready"] += 1

    save_catalog(cat, stamp=stamp)
    return summary


def _default_rehost(url: str, product_id: str) -> tuple[str, str] | None:
    """Download the Gelato image bytes and re-host them SAME-ORIGIN under the
    output dir, returning ``(local_src, sha256)``. Never a Gelato URL leaves here.
    Best-effort: returns None on any failure (caller marks the product error)."""
    import hashlib
    try:
        import requests
        from quoteforge.config import OUTPUT_DIR
    except Exception:  # noqa: BLE001
        return None
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200 or not r.content:
            return None
        data = r.content
        fp = hashlib.sha256(data).hexdigest()
        dest_dir = Path(OUTPUT_DIR) / "mockups"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{product_id}.jpg"
        dest.write_bytes(data)
        # Return the LOCAL master path; the storefront build re-emits it into
        # docs/assets (same-origin) — a Gelato URL never reaches the page.
        return (str(dest), fp)
    except Exception:  # noqa: BLE001
        return None


# ── Confirmation (the two agents) + publish ───────────────────────────────────

def apply_verdicts(product_id: str, *, review: str | None = None,
                   match: str | None = None, reasons: dict | None = None,
                   stamp: str | None = None) -> None:
    """Record an agent verdict. ``review`` ∈ {PASS,HOLD}; ``match`` ∈ {MATCH,MISMATCH}.
    Called by the confirm step after the gelato-mockup-reviewer /
    gelato-sku-image-match agents run."""
    cat = load_catalog()
    rec = cat["products"].get(product_id)
    if not rec:
        return
    if review is not None:
        rec["review"] = {"verdict": review,
                         "reasons": (reasons or {}).get("review"), "at": stamp}
    if match is not None:
        rec["match"] = {"verdict": match,
                        "reasons": (reasons or {}).get("match"), "at": stamp}
    save_catalog(cat, stamp=stamp)


def confirm(*, stamp: str | None = None) -> dict:
    """Compute confirmation from the two agents' verdicts. A product is
    ``confirmed`` only when review==PASS and match==MATCH; else it is ``held``.
    Never confirms a product without both verdicts present."""
    cat = load_catalog()
    summary = {"confirmed": 0, "held": 0, "pending": 0}
    for pid, rec in cat["products"].items():
        if rec.get("status") not in ("ready", "held", "published"):
            continue
        # PROVENANCE GATE (before verdicts): the candidate image's proven origin UID
        # must equal both the record's gelato_uid AND the SKU's currently-resolved real
        # UID. A None / mismatched origin (stale DB row, display-only override, a remap)
        # is HELD and can never publish — so a wrong-product photo cannot reach live.
        cand = rec.get("candidate") or {}
        prov_uid = cand.get("resolved_uid")
        real_uid = _real_uid(rec.get("sku", ""))
        if not (prov_uid and prov_uid == rec.get("gelato_uid") and prov_uid == real_uid):
            rec["confirmed"] = False
            rec["status"] = "held"
            rec["hold_reason"] = "provenance: image origin UID != SKU's real UID"
            summary["held"] += 1
            continue
        rv = (rec.get("review") or {}).get("verdict")
        mv = (rec.get("match") or {}).get("verdict")
        if rv is None or mv is None:
            rec["confirmed"] = False
            if rec.get("status") == "ready":
                rec["status"] = "ready"
            summary["pending"] += 1
            continue
        if rv == "PASS" and mv == "MATCH":
            rec["confirmed"] = True
            rec["confirmed_by"] = "agents"
            rec["confirmed_at"] = stamp
            rec["status"] = "confirmed"
            summary["confirmed"] += 1
        else:
            rec["confirmed"] = False
            rec["status"] = "held"
            summary["held"] += 1
    save_catalog(cat, stamp=stamp)
    return summary


def publish(*, stamp: str | None = None) -> dict:
    """Promote every confirmed product's candidate into its ``live`` block (what
    the storefront reads). Unconfirmed products are never touched."""
    cat = load_catalog()
    summary = {"published": 0}
    for pid, rec in cat["products"].items():
        if rec.get("confirmed") and rec.get("candidate"):
            rec["live"] = dict(rec["candidate"])
            rec["status"] = "published"
            summary["published"] += 1
    save_catalog(cat, stamp=stamp)
    return summary


def override(product_id: str, action: str, *, stamp: str | None = None) -> bool:
    """Human escape hatch only. action ∈ {approve, hold}."""
    cat = load_catalog()
    rec = cat["products"].get(product_id)
    if not rec:
        return False
    if action == "approve" and rec.get("candidate"):
        rec["confirmed"] = True; rec["confirmed_by"] = "human"
        rec["confirmed_at"] = stamp; rec["status"] = "confirmed"
    elif action == "hold":
        rec["confirmed"] = False; rec["status"] = "held"
    else:
        return False
    save_catalog(cat, stamp=stamp)
    return True


# ── What the storefront build consumes ────────────────────────────────────────

def live_mockups() -> dict:
    """name → {src, area, cyl, span} for every CONFIRMED+PUBLISHED product. This is
    the ONLY thing the storefront reads — so an unconfirmed product can never show.
    Keyed by product NAME (what the editor's CURGARMENT carries), like the
    brand/mockups manifest, so `_mockBase` consumes it with zero new shape."""
    out: dict[str, dict] = {}
    cat = load_catalog()
    for pid, rec in cat.get("products", {}).items():
        live = rec.get("live")
        name = rec.get("name")
        # REMAP INVALIDATION (Finding 3): only serve a published photo whose proven
        # origin UID still equals the SKU's currently-resolved real UID. If the owner
        # remapped the SKU to a new Gelato UID, the old photo's bound uid no longer
        # matches -> it is dropped, never served (same guarantee as the uid-bound cache).
        if not (rec.get("confirmed") and live and live.get("src") and name):
            continue
        if live.get("resolved_uid") and live["resolved_uid"] == _real_uid(rec.get("sku", "")):
            out[name] = {"src": live["src"], "area": live.get("area"),
                         "cyl": bool(live.get("cyl")), "span": float(live.get("span", 1.9))}
    return out


def _economics_by_pid() -> dict:
    """product_id → (cheapest sale price, its gelato cost) from each family's
    variations, so the readiness gate can margin-check every product. Never raises
    on one family."""
    out: dict[str, tuple[float, float]] = {}

    def _add(variants) -> None:
        """Fold a family's variants into the cheapest (price, cost) per product_id."""
        for v in variants or []:
            pid = getattr(v, "product_id", None) or getattr(v, "garment_id", None)
            price, cost = getattr(v, "price", None), getattr(v, "gelato_cost", None)
            if pid is None or price is None or cost is None:
                continue
            cur = out.get(pid)
            if cur is None or float(price) < cur[0]:
                out[pid] = (float(price), float(cost))

    for mod, fn in (("mug_catalog", "build_mug_variations"),
                    ("branded_catalog", "build_branded_variations"),
                    ("calendar_catalog", "build_calendar_variations"),
                    ("apparel_catalog", "build_apparel_variations")):
        try:
            m = __import__(f"quoteforge.etsy.{mod}", fromlist=[fn])
            _add(getattr(m, fn)())
        except Exception:  # noqa: BLE001 — a family without variations just won't economics-check
            continue
    return out


def readiness(*, floor_pct: float | None = None) -> list[dict]:
    """The go-live gate, per product, tying the three things that must be right
    before flipping live:
      * **preview** — a CONFIRMED real-product photo (the view matches what Gelato
        delivers). 'pending' until the live daily sync confirms it.
      * **sku** — the SKU resolves to a real (non-placeholder) Gelato UID, so the
        order routes to the right product at fulfilment.
      * **margin** — the cheapest sale price still clears the margin floor.
    Returns per-product rows with a ``go`` flag + blocking ``reasons``. Pure read."""
    try:
        from quoteforge.etsy.margin_guard import margin_check
    except Exception:  # noqa: BLE001
        margin_check = None
    cat = load_catalog()
    econ = _economics_by_pid()
    rows: list[dict] = []
    for prod in all_products():
        pid, name, sku = prod["product_id"], prod["name"], prod["sku"]
        uid = _real_uid(sku)
        sku_ok = uid is not None
        rec = cat.get("products", {}).get(pid, {})
        if rec.get("confirmed"):
            preview = "confirmed"
        elif rec.get("status") == "held":
            preview = "held"
        else:
            preview = "pending"
        margin_ok = None
        margin_pct = None
        pc = econ.get(pid)
        if pc and margin_check is not None:
            m = margin_check(pc[0], pc[1], floor_pct)
            margin_ok = bool(m.get("ok"))
            margin_pct = m.get("margin_pct")
        reasons = []
        if not sku_ok:
            reasons.append("SKU has no real Gelato UID (order would not route)")
        if preview != "confirmed":
            reasons.append(f"preview {preview} (no confirmed real-product photo yet)")
        if margin_ok is False:
            reasons.append(f"margin {margin_pct:.0f}% below floor")
        go = bool(sku_ok and preview == "confirmed" and margin_ok is not False)
        rows.append({"product_id": pid, "name": name, "category": prod["category"],
                     "sku_ok": sku_ok, "preview": preview, "margin_ok": margin_ok,
                     "margin_pct": margin_pct, "go": go, "reasons": reasons})
    return rows


def agent_pending() -> list[str]:
    """Product ids sitting at READY with a candidate but at least one MISSING agent
    verdict — i.e. the two confirming agents have not run over them yet. When we are
    live-gated, a non-empty list means Path A is STALLED (real photos can't publish
    until the gelato-mockup-reviewer + gelato-sku-image-match verdicts are recorded);
    the daily confirm step alerts on it so the stall is loud, never silent."""
    cat = load_catalog()
    out: list[str] = []
    for pid, rec in cat.get("products", {}).items():
        if rec.get("status") != "ready" or not rec.get("candidate"):
            continue
        rv = (rec.get("review") or {}).get("verdict")
        mv = (rec.get("match") or {}).get("verdict")
        if rv is None or mv is None:
            out.append(pid)
    return out


def review_rows() -> list[dict]:
    """Flat per-product status for the `mockup-review` table / the daily email."""
    cat = load_catalog()
    rows = []
    for pid, rec in sorted(cat.get("products", {}).items()):
        rows.append({
            "product_id": pid,
            "category": rec.get("category"),
            "status": rec.get("status"),
            "review": (rec.get("review") or {}).get("verdict"),
            "match": (rec.get("match") or {}).get("verdict"),
            "confirmed": bool(rec.get("confirmed")),
            "live": bool(rec.get("live")),
        })
    return rows
