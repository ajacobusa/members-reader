"""Route an order to the right vendor's fulfillment automatically.

Picks the adapter by the order's `vendor`:
  gelato            -> Gelato API (existing)
  printful          -> Printful API
  printify          -> Printify API
  digital/service/local/unknown -> 'manual' (flagged for you; nothing auto-sent)

API adapters are key-gated and TEST_MODE-safe, so this is a no-op until you add
the relevant vendor key - then non-Gelato products auto-route too.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# Per-order routing locks: two concurrent duplicate webhooks each spawn a daemon
# thread that runs the pipeline and reaches route_order. Without serialization both
# can read vendor_order_id=None and BOTH submit to the supplier (duplicate print +
# charge). A per-order lock makes the critical section (dedup-check -> submit ->
# store) atomic within the process; the loser re-reads the now-stored vendor id and
# is blocked as a duplicate. Pure in-memory: no DB sentinel that a mid-submit crash
# could strand the order on.
_ROUTE_LOCKS: dict = {}
_ROUTE_LOCKS_GUARD = threading.Lock()


def _route_lock(order_id: str) -> threading.Lock:
    """The lock guarding routing for one order id (created on first use)."""
    with _ROUTE_LOCKS_GUARD:
        lk = _ROUTE_LOCKS.get(order_id)
        if lk is None:
            lk = _ROUTE_LOCKS[order_id] = threading.Lock()
        return lk


def route_order(order: dict, recipient: dict = None, artwork_url: str = "") -> dict:
    """Send the order to its vendor's API, serialized per order id so concurrent
    duplicate deliveries can't double-submit. Thin wrapper around the impl."""
    order_id = order.get("order_id") or order.get("etsy_order_id") or ""
    if not order_id:
        return _route_order_impl(order, recipient, artwork_url)
    with _route_lock(order_id):
        return _route_order_impl(order, recipient, artwork_url)


def _has_extra_print_area(order: dict) -> bool:
    """True if this order carries a designed BACK or SLEEVE area (so it must never print
    front-only). Checks the order's recorded extra-print upcharge first, then the linked
    design's per-side flags. Best-effort: a lookup miss returns False without blocking."""
    try:
        if float(order.get("extra_print") or 0) > 0:
            return True
    except (TypeError, ValueError):
        logger.debug("extra_print not numeric on %s: %r",
                     order.get("order_id"), order.get("extra_print"))
    sides = order.get("sides")
    if not isinstance(sides, dict):
        try:
            from quoteforge.db.database import get_design_for_order
            d = get_design_for_order(order.get("order_id") or "") or {}
            sides = d.get("sides") or (d.get("design") or {}).get("sides") or {}
        except Exception as exc:  # noqa: BLE001 - never block routing on a lookup miss,
            # but LOUD not silent: a missed design lookup means we can't see extra areas.
            logger.warning("multi-area design lookup failed for %s: %s",
                           order.get("order_id"), exc)
            sides = {}
    return any((sides or {}).get(a) for a in ("back", "sleeve-left", "sleeve-right"))


def _route_order_impl(order: dict, recipient: dict = None, artwork_url: str = "") -> dict:
    """Send the order to its vendor's API (gelato/printful/printify)."""
    vendor = (order.get("vendor") or "gelato").lower()
    order_id = order.get("order_id") or order.get("etsy_order_id") or ""
    recipient = recipient or order.get("recipient_address") or {}

    # Idempotency: never double-submit. If this order already carries a supplier
    # order id, it is already routed - return that instead of creating a duplicate.
    if order_id:
        from quoteforge.db.database import get_order
        try:
            existing = get_order(order_id)
        except Exception as exc:  # noqa: BLE001
            # If the dedup lookup fails we must NOT proceed - routing anyway could
            # double-submit (double supplier charge). Fail safe and surface it.
            import logging
            logging.getLogger(__name__).warning(
                "route_order dedup lookup failed for %s: %s", order_id, exc)
            return {"status": "error", "vendor": vendor, "id": "",
                    "detail": f"dedup lookup failed; not routing to avoid a "
                              f"duplicate submission: {exc}"}
        if existing and existing.get("vendor_order_id"):
            return {"status": "duplicate", "vendor": vendor,
                    "id": existing["vendor_order_id"],
                    "detail": "order already routed - duplicate submission blocked"}
        if existing and existing.get("status") == "submit_unconfirmed":
            # A prior send timed out AFTER the POST - the vendor may already have
            # this order. Never blindly re-submit; hold for manual reconciliation.
            return {"status": "manual", "vendor": vendor, "id": "",
                    "detail": "previous send was unconfirmed (possible duplicate at "
                              "the vendor) - reconcile before re-sending"}

    if vendor == "gelato":
        from quoteforge.config import (TEST_MODE, GELATO_FULFILLMENT_MODE,
                                        APPAREL_PRINT_CALIBRATED)
        # NATIVE Etsy<->Gelato fulfilment (default): Gelato pulls the order from Etsy,
        # charges your card, prints + ships, and returns tracking to Etsy. QuoteForge
        # must NOT also submit - that would double-print + double-charge on EVERY
        # order. Record it as natively fulfilled (so the monitor doesn't flag a
        # missing vendor id) and stop here. QuoteForge stays the design / analytics /
        # financials / tracking layer.
        if (GELATO_FULFILLMENT_MODE or "native") == "native":
            try:
                from quoteforge.db.database import update_order, get_order
                if order_id and get_order(order_id):
                    update_order(order_id, vendor="gelato-native",
                                 status="in_production")
            except Exception as exc:  # noqa: BLE001 - best-effort, but never silent
                logger.warning("route_order native-record failed for %s "
                               "(status may not advance to in_production): %s",
                               order_id, exc)
            return {"status": "native", "vendor": "gelato-native", "id": "",
                    "detail": "fulfilled by Gelato's native Etsy integration "
                              "(QuoteForge does not submit)"}
        product_uid = order.get("gelato_product_uid") or order.get("product_uid")
        # Defence in depth: a GEL-* seed placeholder must NEVER be submitted to
        # production. Route to manual so the owner maps the real Gelato UID first
        # (protects both apparel and any print SKU left on a placeholder).
        if product_uid and str(product_uid).upper().startswith("GEL-"):
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "placeholder product UID - map the real Gelato UID "
                              "in GELATO_UID_MAP before fulfilment"}
        # A 12-month calendar is a multi-image product: production needs all 12 month
        # photos (get_design_for_order holds the URLs), which the single-file
        # submission path cannot carry yet. NEVER auto-submit a calendar as cover-only
        # (silent under-delivery / chargeback); hold for manual production instead.
        if str(order.get("product_type", "")).lower() == "calendar":
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "12-month calendar needs multi-image production - "
                              "manual fulfilment (all 12 month photos)"}
        # Multi-area apparel safety (UNCONDITIONAL - independent of any flag): an order
        # that carries a designed BACK or SLEEVE must NEVER be printed front-only. If the
        # per-area files aren't attached, HOLD it for manual two-sided production (like a
        # calendar). This closes the silent under-delivery even if the editor offered a
        # back/sleeve before the automatic per-area submission is wired.
        if not order.get("extra_files") and _has_extra_print_area(order):
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "multi-area apparel (back/sleeve design) - manual two-sided "
                              "production until per-area files are wired"}
        # Preview-vs-print safety (UNCONDITIONAL): the storefront apparel editor's design
        # (photo / wording / template / chest position / rotation) is NOT yet rendered into
        # the print file - the pipeline substitutes a generic poster (render_local_poster),
        # so what the buyer APPROVED is not what would print. Until the faithful
        # clean-composite render is wired, a designed apparel order must NEVER auto-submit a
        # poster in place of the buyer's design. Hold for manual placement. A real per-side
        # print file (extra_files) OR an explicit faithful_artwork flag (set once the
        # composite render is wired) is the escape hatch.
        if (str(order.get("product_type", "")).lower() == "apparel"
                and not order.get("extra_files")
                and not order.get("faithful_artwork")):
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "apparel design not yet rendered to a faithful print file "
                              "(preview != print) - hold for manual placement until the "
                              "clean-composite render is wired"}
        # Calibration gate (#167): even WITH faithful per-side files attached, the on-
        # screen placement -> real DTG print-zone mapping is unverified until the owner
        # runs a physical Gelato test print. Until APPAREL_PRINT_CALIBRATED=true, an
        # apparel order still HOLDS for manual - but now the faithful files ride along,
        # so the manual step is verify-and-submit, not build-from-scratch. This makes a
        # mis-calibrated mapping physically incapable of auto-printing on real garments.
        # Apparel is held for manual UNLESS calibration is proven - either the env master
        # APPAREL_PRINT_CALIBRATED (manual owner sign-off) OR the automated path
        # (auto_calibration_active: vision QA passed + owner consent + under the unit cap +
        # NO recent return/dispute). The automated path is fail-safe (False on any doubt)
        # and auto-reverts on the first dispute, so a mis-calibrated mapping still can't
        # keep auto-printing on real garments.
        if str(order.get("product_type", "")).lower() == "apparel" and not APPAREL_PRINT_CALIBRATED:
            _cal_ok = False
            try:
                from quoteforge.automation.calibration_pipeline import auto_calibration_active
                _cal_ok = auto_calibration_active()
            except Exception:  # noqa: BLE001 - unavailable pipeline -> stay blocked (safe)
                _cal_ok = False
            if not _cal_ok:
                return {"status": "manual", "vendor": "gelato", "id": "",
                        "detail": "apparel faithful print files attached; held for print-"
                                  "calibration sign-off (owner APPAREL_PRINT_CALIBRATED, or "
                                  "automated vision-QA calibration within its safety rails)"}
        if not (product_uid and recipient and artwork_url):
            return {"status": "manual", "vendor": "gelato",
                    "detail": "missing product/address/artwork - manual upload",
                    "id": ""}
        # Artwork must be a PUBLIC http(s) URL Gelato can fetch - a local file:// or a
        # data: URL would be accepted here and then fail at Gelato. Hold for manual.
        # Only enforced for a REAL submission (TEST_MODE mocks the call, no fetch).
        if not TEST_MODE and not str(artwork_url).lower().startswith(("http://", "https://")):
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "artwork is not a public URL Gelato can fetch "
                              f"({str(artwork_url)[:40]}...) - host it first"}
        # Normalise + validate the ship-to BEFORE creating the order, so a bad
        # address is fixed/flagged here instead of returning-to-sender later.
        from quoteforge.fulfillment.gelato_returns import normalize_recipient
        norm = normalize_recipient(recipient)
        if not norm["valid"]:
            return {"status": "manual", "vendor": "gelato", "id": "",
                    "detail": "address incomplete (" + ", ".join(norm["issues"])
                    + ") - verify to prevent return-to-sender"}
        recipient = norm["recipient"]
        # Persist the validated ship-to so a later replacement reprint can reuse
        # it without re-collecting the address.
        try:
            import json
            from quoteforge.db.database import update_order, get_order
            if get_order(order_id):
                update_order(order_id, ship_to=json.dumps(recipient))
        except Exception as exc:  # noqa: BLE001 - best-effort, never block routing, never silent
            logger.warning("route_order ship_to persist failed for %s "
                           "(a later reprint will re-collect the address): %s",
                           order_id, exc)
        try:
            from quoteforge.automation.gelato_api import create_gelato_order
            # Submit the ORDERED quantity (was defaulting to 1 -> a qty>1 order
            # shipped only one unit: silent under-delivery / chargeback risk). The
            # orchestrator passes a thin order dict, so fall back to the persisted row.
            qty = order.get("quantity")
            if qty is None and order_id:
                from quoteforge.db.database import get_order as _get_order
                qty = (_get_order(order_id) or {}).get("quantity")
            resp = create_gelato_order(order_id=order_id, recipient=recipient,
                                       artwork_url=artwork_url, product_uid=product_uid,
                                       quantity=int(qty or 1),
                                       shipment_method=order.get("shipment_method") or "",
                                       extra_files=order.get("extra_files") or None)
            vid = resp.get("id", "")
            # Self-store the supplier order id on success so the idempotency guard
            # is robust even if the caller forgets to persist it.
            try:
                from quoteforge.db.database import update_order, get_order
                if vid and get_order(order_id):
                    update_order(order_id, vendor_order_id=vid)
            except Exception as exc:  # noqa: BLE001 - log LOUDLY: a silent failure here
                # leaves the order submitted but without a stored vendor_order_id, so
                # the idempotency guard (above) can't see it and a re-run could
                # double-submit. Surface it; the caller is still expected to persist vid.
                logger.warning("route_order could NOT self-store vendor_order_id %s "
                               "for %s - dedup now relies on the caller persisting "
                               "it: %s", vid, order_id, exc)
            return {"status": "submitted", "vendor": "gelato",
                    "id": vid, "raw": resp}
        except Exception as exc:  # noqa: BLE001
            # Distinguish a CONFIRMED non-submission (safe to retry) from an
            # AMBIGUOUS post-send failure: a timeout / dropped connection / 5xx
            # AFTER the POST means Gelato may already have the order, so a blind
            # re-run would double-print + double-charge. Mark those
            # 'submit_unconfirmed' + persist it, so a re-run holds for manual
            # reconciliation (below) instead of re-creating.
            import requests as _rq
            ambiguous = isinstance(exc, (_rq.exceptions.Timeout,
                                         _rq.exceptions.ConnectionError))
            if isinstance(exc, _rq.exceptions.HTTPError) \
                    and getattr(getattr(exc, "response", None), "status_code", 0) >= 500:
                ambiguous = True
            if ambiguous:
                try:
                    from quoteforge.db.database import update_order, get_order
                    if get_order(order_id):
                        update_order(order_id, status="submit_unconfirmed")
                except Exception as exc:  # noqa: BLE001 - log LOUDLY: if this status
                    # doesn't persist, a re-run won't see 'submit_unconfirmed' and may
                    # blindly re-submit an order the vendor may already have.
                    logger.warning("route_order could NOT persist submit_unconfirmed "
                                   "for %s - a re-run may re-submit a possibly-received "
                                   "order: %s", order_id, exc)
                return {"status": "submit_unconfirmed", "vendor": "gelato", "id": "",
                        "detail": "vendor send unconfirmed (may already be received) - "
                                  f"reconcile before re-sending: {exc}"}
            return {"status": "error", "vendor": "gelato", "detail": str(exc), "id": ""}

    if vendor == "printful":
        from quoteforge.fulfillment import printful
        return printful.create_order(order_id, recipient, artwork_url,
                                     order.get("variant_id"))
    if vendor == "printify":
        from quoteforge.fulfillment import printify
        return printify.create_order(order_id, recipient, artwork_url,
                                     line_items=order.get("line_items", []))
    if vendor == "digital":
        return {"status": "fulfilled", "vendor": "digital",
                "detail": "digital item - delivered electronically", "id": ""}
    return {"status": "manual", "vendor": vendor,
            "detail": f"{vendor}: fulfill by hand", "id": ""}
