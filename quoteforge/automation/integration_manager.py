"""Integration Manager — one unified credential-lifecycle component.

Enterprise onboarding pattern: after a one-time owner setup, no engineer should touch
credentials again. This module UNIFIES the credential checks that already existed as
scattered probes (Gelato auth, Etsy auth, token refresh/expiry, store id, UID mappings)
behind a single ``doctor()`` aggregator, and ADDS the missing pieces: a granted-vs-
required Etsy scope diff and a machine-readable GO / FIX-FIRST verdict with the exact
blocker. The daily scheduler records its health and alerts on any regression, so a
silently-expired token or a revoked scope surfaces before it fails a customer order.

Guard rails:
  * **Never handles plaintext secrets.** It reads booleans/statuses and live-probes with
    the already-configured credentials; it never accepts, prints, or logs a key/token.
  * **No-op safe in TEST_MODE.** Every component skips to ok=True with a note when not
    live, so a fresh install never false-alarms; ``doctor()`` marks the run test_mode.
  * **Fail-fast is the caller's call.** ``doctor()`` returns the verdict; the admin
    command returns non-zero only when live AND a blocker exists.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _scope_diff(granted: str, required: str) -> dict:
    """Pure diff of two space-separated scope strings: which REQUIRED scopes are absent
    from GRANTED. Deterministic, no config/network - the testable core of scope_status."""
    grant = sorted(s for s in (granted or "").split() if s)
    req = sorted(s for s in (required or "").split() if s)
    return {"granted": grant, "required": req, "missing": sorted(set(req) - set(grant))}


def scope_status() -> dict:
    """Diff the Etsy scopes GRANTED to the connected token against the REQUIRED set
    (ETSY_OAUTH_SCOPES), with no network call. {ok, warn, detail, granted, required,
    missing}. Skips (ok) in TEST_MODE / not connected; a LIVE token whose granted set is
    unknown (env-seed / pre-capture) is ok but WARN (nudge to reconnect - not a silent
    PASS); a genuine live token MISSING a required scope is the only not-ok case."""
    from quoteforge.config import TEST_MODE, ETSY_API_KEY, ETSY_OAUTH_SCOPES
    from quoteforge.automation.etsy_auth import current_granted_scopes, current_access_token
    required = _scope_diff("", ETSY_OAUTH_SCOPES)["required"]
    if TEST_MODE or not ETSY_API_KEY or not current_access_token():
        return {"ok": True, "warn": False, "detail": "skipped (TEST_MODE / not connected)",
                "granted": [], "required": required, "missing": []}
    if not current_granted_scopes().split():
        return {"ok": True, "warn": True,   # connected but scopes UNKNOWN -> visible WARN
                "detail": "granted scopes UNKNOWN (env-seed / pre-capture token) - "
                "reconnect via etsy-connect so scopes can be verified",
                "granted": [], "required": required, "missing": []}
    d = _scope_diff(current_granted_scopes(), ETSY_OAUTH_SCOPES)
    return {"ok": not d["missing"], "warn": False,
            "detail": ("all required scopes granted" if not d["missing"]
                       else f"missing required scope(s): {', '.join(d['missing'])}"), **d}


def _store_status() -> dict:
    """Is a Gelato ecommerce store id configured (and usable)? Presence-level, no
    network. {ok, detail}. Skips (ok) in TEST_MODE."""
    from quoteforge.config import TEST_MODE, GELATO_STORE_ID
    if TEST_MODE:
        return {"ok": True, "detail": "skipped (TEST_MODE)"}
    if not (GELATO_STORE_ID or "").strip():
        return {"ok": False, "detail": "GELATO_STORE_ID not set (needed for official "
                "image pull + listing publish)"}
    try:
        from quoteforge.automation.ecommerce_images import _gate
        enabled, sid = _gate()
        return {"ok": bool(enabled and sid),
                "detail": f"store {sid} configured" if enabled
                else "store id set but not live-gated"}
    except Exception as exc:  # noqa: BLE001 - a gate blip is a not-ok, surfaced
        return {"ok": False, "detail": f"store check failed: {exc}"}


# The components that must be green for a GO when live (skips are green in TEST_MODE).
_COMPONENT_ORDER = ("gelato_auth", "gelato_uids", "etsy_auth", "etsy_token",
                    "etsy_scopes", "gelato_store", "credential_encryption", "anthropic_key")


def doctor(*, probe: bool = True) -> dict:
    """One-shot integration health across every credential/integration the shop needs.
    Returns ``{ok, verdict, test_mode, components:{name:{ok,detail,...}}, blockers:[...]}``.
    verdict is 'GO' when nothing blocks, else 'FIX-FIRST'. Never raises; a failing probe
    becomes a not-ok component, not an exception.

    ``probe=True`` (default, the daily CLI run) makes LIVE auth calls to Gelato + Etsy.
    ``probe=False`` (the hermetic infra-check invariant + tests) skips those two network
    calls and reports key/token PRESENCE instead - so the daily invariant never depends
    on the network."""
    from quoteforge.config import TEST_MODE, ANTHROPIC_API_KEY
    comps: dict[str, dict] = {}

    def _safe(name: str, fn) -> None:
        """Run one probe; any exception is a not-ok component, never a crash."""
        try:
            comps[name] = fn()
        except Exception as exc:  # noqa: BLE001 - a probe crash is itself a blocker
            comps[name] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    if probe:
        _safe("gelato_auth", lambda: _import("quoteforge.automation.gelato_api",
                                             "verify_gelato_auth")())
    else:
        from quoteforge.config import GELATO_API_KEY
        comps["gelato_auth"] = {"ok": bool(GELATO_API_KEY),
                                "detail": "key set (live probe skipped)" if GELATO_API_KEY
                                else "GELATO_API_KEY not set"}

    def _uids() -> dict:
        m = _import("quoteforge.etsy.gelato_catalog", "verify_catalog_mappings")()
        return {"ok": bool(m.get("all_real")),
                "detail": f"all {m.get('total')} UID mappings real" if m.get("all_real")
                else f"{m.get('placeholder_count')}/{m.get('total')} placeholder UID(s) "
                "- replace with real Gelato UIDs"}
    _safe("gelato_uids", _uids)

    if probe:
        _safe("etsy_auth", lambda: _import("quoteforge.automation.etsy_auth",
                                           "verify_etsy_auth")())
    else:
        from quoteforge.config import TEST_MODE as _tm, ETSY_API_KEY
        from quoteforge.automation.etsy_auth import current_access_token
        _connected = bool(ETSY_API_KEY and current_access_token())
        comps["etsy_auth"] = {"ok": bool(_tm or not ETSY_API_KEY or _connected),
                              "detail": "connected (live probe skipped)" if _connected
                              else "skipped (TEST_MODE / not connected)"}
    _safe("etsy_token", lambda: _import("quoteforge.automation.etsy_auth",
                                        "token_expiry_status")())
    _safe("etsy_scopes", scope_status)
    _safe("gelato_store", _store_status)
    _safe("credential_encryption",
          lambda: _import("quoteforge.automation.secret_store", "encryption_status")())
    comps["anthropic_key"] = {"ok": bool(ANTHROPIC_API_KEY),
                              "detail": "set" if ANTHROPIC_API_KEY else "ANTHROPIC_API_KEY not set"}

    blockers = [f"{k}: {comps[k].get('detail')}"
                for k in _COMPONENT_ORDER if not comps.get(k, {}).get("ok", False)]
    warns = [f"{k}: {comps[k].get('detail')}"
             for k in _COMPONENT_ORDER if comps.get(k, {}).get("warn")]
    return {"ok": not blockers, "verdict": "GO" if not blockers else "FIX-FIRST",
            "test_mode": bool(TEST_MODE), "components": comps,
            "blockers": blockers, "warns": warns}


def _import(module: str, name: str):
    """Import one attribute lazily (keeps import graph light + testable)."""
    mod = __import__(module, fromlist=[name])
    return getattr(mod, name)


def format_report(d: dict | None = None) -> str:
    """Human-readable doctor report for the CLI (no secrets)."""
    d = d or doctor()
    lines = [f"Integration health - {d['verdict']}"
             + ("  (TEST_MODE: informational, live checks skipped)" if d["test_mode"] else ""),
             "=" * 60]
    for name in _COMPONENT_ORDER:
        c = d["components"].get(name, {})
        mark = "WARN" if c.get("warn") else ("PASS" if c.get("ok") else "FIX ")
        lines.append(f"  [{mark}] {name:18} {c.get('detail', '')}")
    if d["blockers"]:
        lines.append("-" * 60)
        lines.append("BLOCKERS (fix before go-live):")
        for b in d["blockers"]:
            lines.append(f"   - {b}")
    if d.get("warns"):
        lines.append("-" * 60)
        lines.append("WARNINGS (non-blocking, worth resolving):")
        for w in d["warns"]:
            lines.append(f"   - {w}")
    return "\n".join(lines)


def setup_checklist() -> list[dict]:
    """Ordered onboarding steps and whether each is genuinely CONFIGURED (not merely
    health-skipped) - so it reads truthfully even in TEST_MODE. [{step, done, how}], most-
    foundational first. The guided complement to doctor(): doctor says what's unhealthy;
    this says what the owner still has to set up."""
    from quoteforge.config import (ANTHROPIC_API_KEY, GELATO_API_KEY, GELATO_STORE_ID,
                                   ETSY_API_KEY)
    from quoteforge.automation.etsy_auth import current_access_token, current_refresh_token
    connected = bool(ETSY_API_KEY and current_access_token() and current_refresh_token())
    try:
        m = _import("quoteforge.etsy.gelato_catalog", "verify_catalog_mappings")()
        uids_real = bool(m.get("all_real"))
    except Exception:  # noqa: BLE001 - unreadable mapping counts as not-done
        uids_real = False
    scopes_ok = connected and not scope_status().get("missing")
    steps = [
        ("Set ANTHROPIC_API_KEY", bool(ANTHROPIC_API_KEY),
         "add ANTHROPIC_API_KEY to the environment"),
        ("Set GELATO_API_KEY", bool(GELATO_API_KEY),
         "add GELATO_API_KEY, then `admin verify-keys`"),
        ("Replace placeholder Gelato UIDs", uids_real,
         "map real UIDs (draft->verify->approve), then `admin verify-keys`"),
        ("Set GELATO_STORE_ID", bool((GELATO_STORE_ID or '').strip()),
         "connect the Etsy store in Gelato, put its id in GELATO_STORE_ID"),
        ("Connect Etsy (OAuth)", connected,
         "`admin etsy-connect start`, authorize, `admin etsy-connect finish <code>`"),
        ("Grant all required Etsy scopes", bool(scopes_ok),
         "re-run etsy-connect if a scope is missing"),
    ]
    return [{"step": s, "done": bool(done), "how": how} for s, done, how in steps]
