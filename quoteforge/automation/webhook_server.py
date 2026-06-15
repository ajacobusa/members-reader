"""
Zapier/Make.com webhook receiver for automated Etsy order processing.

Setup:
1. pip install flask
2. Run: python -m quoteforge.automation.webhook_server
3. In Zapier: New Etsy Order → Webhook POST to http://your-ip:5050/order
4. Zapier sends JSON with order personalization fields
5. QuoteForge auto-generates the quote and saves it

Zapier JSON format expected:
{
  "customer_name": "Jennifer Smith",
  "recipient_name": "Emma",
  "relationship": "To My Daughter",
  "occasion": "Graduation",
  "scenery": "Mountains",
  "tone": "Inspirational & Motivational",
  "memory": "She worked so hard for four years...",
  "output_style": "Personal Letter",
  "order_id": "12345678",
  "item_title": "Personalized Daughter Gift Print"
}
"""
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from quoteforge.config import OUTPUT_DIR

app = Flask(__name__) if FLASK_AVAILABLE else None

# Upload cap: a poster-quality JPG is well under this; bigger is abuse/error.
MAX_UPLOAD_MB = 25

WEBHOOK_LOG = OUTPUT_DIR / "webhook_log.json"


_log_lock = threading.Lock()


def _append_webhook_log(entry: dict) -> None:
    """Append a log entry atomically (lock + atomic file replace).

    Prevents concurrent webhook requests from losing/corrupting entries.
    """
    with _log_lock:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        entries = []
        if WEBHOOK_LOG.exists():
            try:
                entries = json.loads(WEBHOOK_LOG.read_text())
            except Exception:
                entries = []
        entries.append(entry)
        # write to temp then atomically replace — never leaves a half-written file
        tmp = WEBHOOK_LOG.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, indent=2))
        tmp.replace(WEBHOOK_LOG)


def _parse_money(value) -> float | None:
    """Parse a money value from a webhook (handles '$29.99', '29,99', 29.99)."""
    if value is None or value == "":
        return None
    try:
        s = str(value).replace("$", "").replace(",", "").strip()
        return round(float(s), 2)
    except (ValueError, TypeError):
        return None


# Order-level fields shared by every line item in a multi-item order.
_ORDER_LEVEL = ("customer_name", "customer_email", "sale_price", "price",
                "total", "order_total", "grandtotal", "shipping_address")


def _build_order_data(item: dict, etsy_order_id: str) -> dict:
    """Map a (line-item) payload to the pipeline's order_data shape."""
    return {
        "etsy_order_id": etsy_order_id,
        "order_id": item.get("order_id") or etsy_order_id,
        "customer_name": item.get("customer_name", ""),
        "customer_email": item.get("customer_email", ""),
        "recipient_name": item.get("recipient_name", "Friend"),
        "sender_name": item.get("customer_name", "Anonymous"),
        "relationship": item.get("relationship", "To My Friend"),
        "occasion": item.get("occasion", "Special Occasion"),
        "scenery": item.get("scenery", "Mountains"),
        "tone": item.get("tone", "Inspirational & Motivational"),
        "memory": item.get("memory", ""),
        "output_style": item.get("output_style", "Personal Letter"),
        "product_size": item.get("product_size") or item.get("size", ""),
        "quantity": int(item.get("quantity", 1) or 1),
        # Buyer-provided custom content (verbatim text + their own photo).
        "custom_text": item.get("custom_text") or item.get("custom_quote", ""),
        "custom_image": item.get("custom_image") or item.get("custom_photo", ""),
        "sale_price": _parse_money(
            item.get("sale_price") or item.get("price") or item.get("item_total")
            or item.get("total") or item.get("order_total") or item.get("grandtotal")),
        "gelato_cost": _parse_money(item.get("gelato_cost")),
        # Real Etsy figures + ship-to destination (from receipt_to_order_payload)
        # so reporting + the shipping-variance audit use actual data.
        "shipping_collected": _parse_money(item.get("shipping_collected")),
        "tax_collected": _parse_money(item.get("tax_collected")),
        "country": item.get("country", ""),
        "state": item.get("state", ""),
    }


def _run_one(item: dict, etsy_order_id: str) -> dict:
    """Idempotently process ONE line item through the full pipeline."""
    from quoteforge.db.database import init_db, get_order_by_etsy_id
    init_db()
    missing = [f for f in ("recipient_name", "occasion") if not item.get(f)]
    if missing:
        return {"status": "error", "etsy_order_id": etsy_order_id,
                "message": f"Missing fields: {missing}"}
    if etsy_order_id and get_order_by_etsy_id(etsy_order_id):
        return {"status": "duplicate", "etsy_order_id": etsy_order_id,
                "message": "Already processed"}
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline
    order_data = _build_order_data(item, etsy_order_id)
    result = run_full_pipeline(order_data)
    _append_webhook_log({
        "timestamp": datetime.now().isoformat(), "order_id": etsy_order_id,
        "internal_order_id": result.get("order_id", ""),
        "recipient": item.get("recipient_name", ""),
        "occasion": item.get("occasion", ""),
        "status": result.get("status", "processed"),
    })
    return {"status": "success", "etsy_order_id": etsy_order_id,
            "internal_order_id": result.get("order_id", ""),
            "pipeline_status": result.get("status", ""),
            "recipient": item.get("recipient_name", "")}


def process_webhook_payload(payload: dict) -> dict:
    """Process an incoming Etsy order webhook through the full pipeline.

    Supports BOTH shapes:
      - single item: personalization fields at the top level.
      - multi-item:  payload['items'] = [ {personalization...}, ... ] — each line
        item is processed independently (its own quote/artwork/proof) under the
        same Etsy order, with per-item idempotency.
    Idempotent and testable without Flask.
    """
    base_id = str(payload.get("order_id") or payload.get("etsy_order_id") or "")
    items = payload.get("items")

    # Auto-grow the owned audience: enroll the buyer's email (idempotent, never
    # fatal). This is the automated counterpart to the email-capture kit.
    try:
        email = payload.get("customer_email", "")
        if email:
            from quoteforge.db.database import add_subscriber
            add_subscriber(email, source="etsy")
    except Exception:  # noqa: BLE001 — list-building must never block an order
        pass

    # Gift e-card: notify the recipient + capture their email (growth loop).
    try:
        if payload.get("gift_recipient_email"):
            from quoteforge.etsy.gift_ecard import send_gift_ecard
            send_gift_ecard(payload)
    except Exception:  # noqa: BLE001
        pass

    # Per-customer folder: persist this customer's info under their customer ID.
    try:
        cust_email = payload.get("customer_email", "")
        if cust_email:
            from quoteforge.customers import record_order
            record_order(cust_email, payload, payload.get("customer_name", ""))
    except Exception:  # noqa: BLE001
        pass

    # Subscription order: create the membership record + welcome email.
    try:
        if payload.get("subscription_plan"):
            from quoteforge.etsy.subscription_product import start_subscription_from_order
            start_subscription_from_order(payload)
    except Exception:  # noqa: BLE001
        pass

    try:
        # ── Multi-item order ────────────────────────────────────
        if isinstance(items, list) and items:
            order_level = {k: payload.get(k) for k in _ORDER_LEVEL
                           if payload.get(k) is not None}
            results = []
            for i, raw in enumerate(items, 1):
                merged = {**order_level, **raw}      # item overrides order-level
                line_id = f"{base_id}-{i}" if base_id else f"item-{i}"
                merged["order_id"] = line_id
                results.append(_run_one(merged, line_id))
            ok = [r for r in results if r["status"] == "success"]
            return {"status": "success" if ok else "error",
                    "order_id": base_id, "items": len(items),
                    "processed": len(ok), "results": results,
                    "message": f"{len(ok)}/{len(items)} line item(s) processed"}

        # ── Single-item order ───────────────────────────────────
        result = _run_one({**payload, "order_id": base_id}, base_id)
        if result["status"] == "error":
            return {"status": "error", "message": result["message"]}
        if result["status"] == "duplicate":
            return {"status": "duplicate", "order_id": base_id,
                    "message": "Order already processed — skipped"}
        return {"status": "success", "order_id": base_id,
                "internal_order_id": result["internal_order_id"],
                "pipeline_status": result["pipeline_status"],
                "message": f"Order processed for {result['recipient']}"}

    except Exception as exc:
        _append_webhook_log({"timestamp": datetime.now().isoformat(),
                             "order_id": base_id, "status": "error",
                             "error": str(exc)})
        return {"status": "error", "message": str(exc)}


def _is_duplicate(etsy_order_id: str) -> bool:
    """Fast synchronous idempotency check (used before async dispatch)."""
    if not etsy_order_id:
        return False
    from quoteforge.db.database import init_db, get_order_by_etsy_id
    init_db()
    return get_order_by_etsy_id(etsy_order_id) is not None


def _process_in_background(payload: dict) -> None:
    """Run the (slow) full pipeline off the request thread."""
    try:
        process_webhook_payload(payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Background order processing failed: {exc}")


# Gelato fulfillment status → our internal order status
_GELATO_STATUS_MAP = {
    # "passed" = Gelato accepted the order into fulfilment. Map straight to
    # in_production (a status every consumer handles) rather than an orphaned
    # "fulfillment_accepted" that order_monitor/financials never recognized.
    "passed": "in_production",
    "in_production": "in_production",
    "printed": "in_production",
    "shipped": "shipped",
    "delivered": "delivered",
    # Normalize BOTH spellings to "cancelled" (two Ls) - the spelling every
    # downstream consumer checks (tracker _TERMINAL, order_monitor, financial
    # reports, delight loop). "canceled" silently stranded the order otherwise.
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "failed": "error",
}


def process_gelato_callback(payload: dict) -> dict:
    """Apply a Gelato status/tracking callback to the matching order.

    Gelato sends `orderReferenceId` (which we set to our own order_id when we
    created the order) plus a fulfillment `status` and, on shipment, a tracking
    code/url. We match on the reference and update status + tracking.
    """
    from quoteforge.db.database import init_db, get_order, update_order
    init_db()
    ref = str(payload.get("orderReferenceId")
              or payload.get("order_reference_id") or "")
    if not ref or not get_order(ref):
        return {"status": "ignored", "reason": "unknown orderReferenceId",
                "reference": ref}

    raw_status = str(payload.get("status") or payload.get("fulfillmentStatus")
                     or "").lower()
    fields: dict = {}
    if raw_status in _GELATO_STATUS_MAP:
        fields["status"] = _GELATO_STATUS_MAP[raw_status]
    tracking = (payload.get("trackingCode") or payload.get("tracking_code")
                or payload.get("trackingNumber") or "")
    if tracking:
        fields["tracking_number"] = tracking
    if not fields:
        return {"status": "ignored", "reason": "no actionable fields",
                "reference": ref}
    update_order(ref, **fields)
    logger.info(f"Gelato callback applied to {ref}: {fields}")

    # Highest-value automation: when Gelato reports tracking, push it straight
    # onto the Etsy receipt so the buyer sees "Shipped" + tracking automatically.
    etsy_push = None
    if tracking:
        try:
            from quoteforge.automation.etsy_api import create_receipt_shipment
            order = get_order(ref)
            receipt_id = (order or {}).get("etsy_order_id") or ref
            carrier = (payload.get("trackingCarrier")
                       or payload.get("carrier") or "other")
            etsy_push = create_receipt_shipment(receipt_id, tracking, carrier)
            logger.info(f"Pushed tracking to Etsy receipt {receipt_id}: "
                        f"{etsy_push.get('status')}")
        except Exception as exc:  # noqa: BLE001 - never fail the callback on this
            logger.error(f"Etsy tracking push failed for {ref}: {exc}")
            etsy_push = {"status": "error", "detail": str(exc)}
    return {"status": "ok", "reference": ref, "updated": fields,
            "etsy_tracking_push": etsy_push}


if FLASK_AVAILABLE and app:
    # Serve the storefront itself so one process hosts BOTH the shop page and the
    # API endpoints it calls (/upload, /ask, ...). Same-origin = no CORS headaches.
    DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"

    @app.route("/", methods=["GET"])
    def storefront():
        """The customer-facing shop home (docs/index.html)."""
        from flask import send_from_directory
        return send_from_directory(DOCS_DIR, "index.html")

    @app.route("/assets/<path:filename>", methods=["GET"])
    def storefront_assets(filename):
        """Static images/assets for the storefront (docs/assets/...)."""
        from flask import send_from_directory
        return send_from_directory(DOCS_DIR / "assets", filename)

    @app.route("/health", methods=["GET"])
    def health():
        """Deep health check — verifies the database is reachable."""
        db_ok = True
        db_error = ""
        try:
            from quoteforge.db.database import init_db, get_order_stats
            init_db()
            get_order_stats()
        except Exception as exc:
            db_ok = False
            db_error = str(exc)
        status = "ok" if db_ok else "degraded"
        code = 200 if db_ok else 503
        return jsonify({
            "status": status,
            "service": "QuoteForge Webhook",
            "database": "ok" if db_ok else f"error: {db_error}",
            "timestamp": datetime.now().isoformat(),
        }), code

    @app.route("/ask", methods=["GET", "POST"])
    def ask():
        """Ask Ange (AI assistant) - grounded answers for the on-page widget.
        GET /ask?q=... or POST {"q": "..."}. CORS-open so the static site can call it."""
        q = (request.args.get("q") if request.method == "GET"
             else (request.get_json(force=True, silent=True) or {}).get("q", ""))
        try:
            from quoteforge.ai.ange import ask_ange
            result = ask_ange(q or "")
        except Exception as exc:  # noqa: BLE001
            result = {"answer": "Sorry, I'm having trouble - please message the team.",
                      "error": str(exc)}
        resp = jsonify(result)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @app.route("/signup", methods=["POST", "OPTIONS"])
    def signup():
        """Email capture for the on-site exit-intent / newsletter form.
        POST {"email": "...", "source": "exit_intent"}. CORS-open so the static
        site can call it. Stored with consent='yes' (explicit form opt-in)."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        data = request.get_json(force=True, silent=True) or {}
        email = (data.get("email") or "").strip()
        source = (data.get("source") or "site").strip()[:40]
        added = False
        try:
            from quoteforge.db.database import add_subscriber
            added = add_subscriber(email, source=source, consent="yes")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"signup failed: {exc}")
        ok = added or ("@" in email and "." in email.split("@")[-1])
        resp = jsonify({"status": "ok" if ok else "error",
                        "added": added})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, (200 if ok else 400)

    @app.route("/files/<path:filename>", methods=["GET"])
    def serve_public_file(filename):
        """Serve a hosted print file so the print partner can fetch it by URL.
        Enabled only when PUBLIC_FILE_DIR is configured."""
        from quoteforge.config import PUBLIC_FILE_DIR
        if not PUBLIC_FILE_DIR:
            return jsonify({"status": "error", "message": "not configured"}), 404
        from flask import send_from_directory
        return send_from_directory(PUBLIC_FILE_DIR, filename)

    @app.route("/upload", methods=["POST", "OPTIONS"])
    def upload_photo():
        """Receive a customer print photo (multipart), AI-check quality, attach it
        to the order. Form fields: file, email, order_id (opt), size (opt).
        Returns the assessment + decision (approve|hold|reject)."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        f = request.files.get("file")
        email = (request.form.get("email") or "").strip()
        order_id = (request.form.get("order_id") or "").strip()
        size = (request.form.get("size") or "18x24").strip()
        if not f or "@" not in email:
            resp = jsonify({"status": "error", "message": "file and email required"})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp, 400
        # Hardening gate BEFORE anything touches disk:
        #  - filename is attacker-controlled: strip any path components
        #  - only print-supported extensions are ever written
        #  - cap the size (a poster-quality JPG is well under 25 MB)
        from werkzeug.utils import secure_filename
        safe_name = secure_filename(f.filename or "") or "upload.jpg"
        from quoteforge.automation.print_quality import SUPPORTED
        if not safe_name.lower().endswith(SUPPORTED):
            resp = jsonify({"status": "error",
                            "message": "unsupported file type - please upload "
                                       "a JPG, PNG, PDF or TIFF"})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp, 400
        max_bytes = MAX_UPLOAD_MB * 1024 * 1024
        if (request.content_length or 0) > max_bytes:
            resp = jsonify({"status": "error",
                            "message": f"file too large - the maximum is "
                                       f"{MAX_UPLOAD_MB} MB"})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp, 413
        try:
            import tempfile, os as _os
            from quoteforge.customers import save_upload
            from quoteforge.automation.print_quality import (assess_photo,
                                                             reupload_request)
            tmp = _os.path.join(tempfile.gettempdir(), safe_name)
            f.save(tmp)
            # Always keep the LOCAL copy in the customer folder.
            saved = save_upload(email, tmp, name=request.form.get("name", ""))
            assessment = assess_photo(saved or tmp, size)
            decision = assessment["decision"]
            # Publish a public, Gelato-fetchable URL (Drive / public dir / local).
            from quoteforge.automation.file_host import publish_print_file
            pub = publish_print_file(saved or tmp)
            if order_id:
                from quoteforge.db.database import update_order
                fields = {"print_file": str(saved or ""), "print_quality": decision,
                          "artwork_url": pub["url"]}
                if decision == "reject":
                    fields["status"] = "hold_photo"
                update_order(order_id, **fields)
            from quoteforge.automation.print_quality import ai_focal_point
            focal = ai_focal_point(saved or tmp)
            out = {"status": "ok", "decision": decision,
                   "reasons": assessment["reasons"],
                   "hosted": pub["public"], "host": pub["host"],
                   "focal": focal}
            if decision != "approve":
                out["message"] = reupload_request(assessment)
            resp = jsonify(out)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"upload_photo failed: {exc}")
            resp = jsonify({"status": "error", "message": "could not process file"})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp, 500
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @app.route("/service-request", methods=["POST", "OPTIONS"])
    def service_request():
        """Customer service/return request intake. Multipart fields: name,
        order_number, email, phone, issue_type, description, delivery_date,
        consent, product_photo(s), packaging_photo(s). Saves any photos,
        validates against the order record, documents the request, and returns
        the individual-review acknowledgement (never reveals the supplier)."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        form = request.form
        email = (form.get("email") or "").strip()
        photos: list = []

        def _save(field: str, label: str) -> None:
            """Persist any uploaded photos for a field and record its label."""
            from werkzeug.utils import secure_filename
            from quoteforge.automation.print_quality import SUPPORTED
            for fobj in request.files.getlist(field):
                if not fobj or not fobj.filename:
                    continue
                nm = secure_filename(fobj.filename or "")
                if not nm.lower().endswith(SUPPORTED):
                    continue
                try:
                    import tempfile, os as _os
                    from quoteforge.customers import save_upload
                    tmp = _os.path.join(tempfile.gettempdir(), nm)
                    fobj.save(tmp)
                    save_upload(email, tmp, name=form.get("name", ""))
                except Exception:  # noqa: BLE001 - a save hiccup must not drop the claim
                    pass
                if label not in photos:
                    photos.append(label)

        _save("product_photo", "product")
        _save("packaging_photo", "packaging")
        req = {"order_number": (form.get("order_number") or "").strip(),
               "name": (form.get("name") or "").strip(), "email": email,
               "phone": (form.get("phone") or "").strip(),
               "issue_type": (form.get("issue_type") or "").strip(),
               "description": (form.get("description") or "").strip(),
               "delivery_date": (form.get("delivery_date") or "").strip(),
               "preferred_resolution": (form.get("preferred_resolution") or "").strip(),
               "photos": photos}
        from quoteforge.fulfillment.claim_service import intake_claim, CUSTOMER_ACK
        try:
            result = intake_claim(req)
            out = {"status": "ok", "message": CUSTOMER_ACK,
                   "recommended_status": result["recommended_status"],
                   "order_matched": bool(result["order_id"])}
        except Exception as exc:  # noqa: BLE001 - always acknowledge the customer
            logger.warning(f"service_request failed: {exc}")
            out = {"status": "received", "message": CUSTOMER_ACK}
        resp = jsonify(out)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @app.route("/design", methods=["POST", "OPTIONS"])
    def save_design_route():
        """Save a customer's design layout (preferences). POST {email, design_id,
        design, summary}."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        d = request.get_json(force=True, silent=True) or {}
        email = (d.get("email") or "").strip()
        saved = 0
        try:
            import json as _json
            from quoteforge.db.database import save_design
            design = d.get("design")
            if design is not None and not isinstance(design, str):
                design = _json.dumps(design)
            saved = save_design(email, design_json=design or "",
                                design_id=d.get("design_id", "default"),
                                summary=d.get("summary", ""))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"save_design failed: {exc}")
        ok = "@" in email
        resp = jsonify({"status": "ok" if ok else "error", "saved": bool(saved)})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, (200 if ok else 400)

    @app.route("/confirm", methods=["POST", "OPTIONS"])
    def confirm_design_route():
        """Customer accepted the final proof. POST {email, summary, design,
        design_id}. Records acceptance + emails a confirmation."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        d = request.get_json(force=True, silent=True) or {}
        email = (d.get("email") or "").strip()
        try:
            import json as _json
            from quoteforge.automation.design_confirm import confirm_design
            design = d.get("design")
            if design is not None and not isinstance(design, str):
                design = _json.dumps(design)
            result = confirm_design(email, summary=d.get("summary", ""),
                                    design_json=design or "",
                                    design_id=d.get("design_id", "default"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"confirm_design failed: {exc}")
            result = {"ok": False, "emailed": False}
        resp = jsonify({"status": "ok" if result.get("ok") else "error",
                        "emailed": result.get("emailed", False)})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, (200 if result.get("ok") else 400)

    @app.route("/ab", methods=["POST", "OPTIONS"])
    def ab_event():
        """Record an A/B impression/conversion. POST {experiment, variant, event}."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        d = request.get_json(force=True, silent=True) or {}
        ok = False
        try:
            from quoteforge.db.database import record_ab_event
            ok = bool(record_ab_event(d.get("experiment", ""), d.get("variant", ""),
                                      d.get("event", ""), d.get("visitor", "")))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"ab_event failed: {exc}")
        resp = jsonify({"status": "ok" if ok else "error"})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, (200 if ok else 400)

    @app.route("/customization", methods=["POST", "OPTIONS"])
    def save_customization_route():
        """Save an in-progress (abandoned) customization for later recovery.
        POST {email, listing, material, size, wording, has_photo, state_json}."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        d = request.get_json(force=True, silent=True) or {}
        saved = 0
        # A 'converted' ping (the shopper added the item to their order) closes the
        # abandoned record so no recovery email is sent.
        if str(d.get("status", "")).lower() == "converted":
            try:
                from quoteforge.db.database import mark_customization
                mark_customization(d.get("email", ""), d.get("listing", ""),
                                   "converted")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"mark converted failed: {exc}")
            resp = jsonify({"status": "ok", "converted": True})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            return resp
        try:
            import json as _json
            from quoteforge.db.database import save_customization
            state = d.get("state_json")
            if state is not None and not isinstance(state, str):
                state = _json.dumps(state)
            saved = save_customization(
                email=d.get("email", ""), listing=d.get("listing", ""),
                material=d.get("material", ""), size=d.get("size", ""),
                wording=d.get("wording", ""), has_photo=bool(d.get("has_photo")),
                state_json=state or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"save_customization failed: {exc}")
        ok = "@" in str(d.get("email", ""))
        resp = jsonify({"status": "ok" if ok else "error", "saved": bool(saved)})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, (200 if ok else 400)

    @app.route("/profile", methods=["POST", "OPTIONS"])
    def save_profile():
        """Save a memory-based gift profile from the storefront.
        POST {owner_email, recipient_name, relationship, occasion, event_date, notes}."""
        if request.method == "OPTIONS":
            resp = jsonify({})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        d = request.get_json(force=True, silent=True) or {}
        saved = 0
        try:
            from quoteforge.db.database import save_gift_profile
            saved = save_gift_profile(
                owner_email=d.get("owner_email", ""),
                recipient_name=d.get("recipient_name", ""),
                relationship=d.get("relationship", ""),
                occasion=d.get("occasion", ""),
                event_date=d.get("event_date", ""),
                notes=d.get("notes", ""))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"save_profile failed: {exc}")
        ok = bool(d.get("owner_email") and d.get("recipient_name"))
        resp = jsonify({"status": "ok" if ok else "error", "saved": bool(saved)})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, (200 if ok else 400)

    @app.route("/order", methods=["POST"])
    def receive_order():
        """Order intake webhook - verify signature, validate, dedupe, then
        process in a background thread (ACK 202 immediately)."""
        from quoteforge.automation.webhook_security import verify_signature
        raw_body = request.get_data()
        signature = request.headers.get("X-Webhook-Signature", "")
        if not verify_signature(raw_body, signature):
            logger.warning("Rejected webhook — invalid signature")
            return jsonify({"status": "error", "message": "Invalid signature"}), 401

        payload = request.get_json(force=True, silent=True) or {}
        etsy_order_id = str(payload.get("order_id") or payload.get("etsy_order_id") or "")
        logger.info(f"Received order webhook: order_id={etsy_order_id}")

        # Validate required fields synchronously (fast feedback to sender)
        missing = [f for f in ("recipient_name", "occasion") if not payload.get(f)]
        if missing:
            return jsonify({"status": "error", "message": f"Missing fields: {missing}"}), 400

        # Idempotency check synchronously — duplicates never spawn work
        if _is_duplicate(etsy_order_id):
            return jsonify({"status": "duplicate", "order_id": etsy_order_id,
                            "message": "Already processed — skipped"}), 200

        # Dispatch the heavy pipeline to a background thread and ACK immediately
        # with 202 Accepted so Make.com/Zapier never times out waiting on us.
        threading.Thread(target=_process_in_background, args=(payload,),
                         daemon=True).start()
        return jsonify({"status": "accepted", "order_id": etsy_order_id,
                        "message": "Order accepted and processing"}), 202

    @app.route("/gelato", methods=["POST"])
    def receive_gelato_callback():
        """Gelato status/tracking webhook — signature-verified, then applied."""
        from quoteforge.automation.webhook_security import verify_gelato_signature
        raw_body = request.get_data()
        signature = (request.headers.get("X-Gelato-Signature")
                     or request.headers.get("X-Webhook-Signature", ""))
        if not verify_gelato_signature(raw_body, signature):
            logger.warning("Rejected Gelato callback — invalid signature")
            return jsonify({"status": "error", "message": "Invalid signature"}), 401
        payload = request.get_json(force=True, silent=True) or {}
        result = process_gelato_callback(payload)
        code = 200 if result["status"] in ("ok", "ignored") else 400
        return jsonify(result), code

    @app.route("/issue", methods=["POST"])
    def receive_issue():
        """Customer-issue intake — autopilot decides: auto-resolve or escalate."""
        from quoteforge.automation.webhook_security import verify_signature
        raw_body = request.get_data()
        signature = request.headers.get("X-Webhook-Signature", "")
        if not verify_signature(raw_body, signature):
            return jsonify({"status": "error", "message": "Invalid signature"}), 401
        payload = request.get_json(force=True, silent=True) or {}
        issue_text = payload.get("issue") or payload.get("message") or ""
        order_id = str(payload.get("order_id") or "") or None
        if not issue_text:
            return jsonify({"status": "error", "message": "Missing 'issue'"}), 400
        from quoteforge.automation.autopilot import handle_issue
        result = handle_issue(issue_text, order_id)
        return jsonify(result), 200

    @app.route("/backup", methods=["POST"])
    def trigger_backup():
        """Create a database snapshot on demand (for scheduled backups)."""
        from quoteforge.db.database import backup_database, prune_old_backups
        path = backup_database()
        prune_old_backups()  # age-based: keep last BACKUP_RETENTION_DAYS days
        return jsonify({
            "status": "ok" if path else "no_database",
            "backup": str(path) if path else "",
        })

    @app.route("/test", methods=["GET"])
    def test_endpoint():
        """Test endpoint — sends a dummy order through the pipeline."""
        dummy = {
            "customer_name": "Test Customer",
            "recipient_name": "Emma",
            "relationship": "To My Daughter",
            "occasion": "Graduation",
            "scenery": "Mountains",
            "tone": "Inspirational & Motivational",
            "memory": "Test order from webhook health check.",
            "output_style": "Custom Quote",
            "order_id": "TEST-001",
        }
        result = process_webhook_payload(dummy)
        return jsonify(result)


def run_server(host: str = "0.0.0.0", port: int = None, debug: bool = False) -> None:
    """Start the webhook server - waitress when available, Flask dev otherwise."""
    # Hosts (Render/Railway/Fly/Heroku) inject the port via $PORT.
    if port is None:
        port = int(os.getenv("PORT", "5050"))
    if not FLASK_AVAILABLE:
        print("Flask not installed. Run: pip install flask")
        return
    logger.info(f"QuoteForge Webhook Server starting on {host}:{port}")
    logger.info("Zapier/Make.com: POST to http://YOUR-IP:5050/order")

    try:
        from quoteforge.automation.monitoring import init_monitoring
        if init_monitoring():
            logger.info("Sentry error monitoring active")
    except Exception:  # noqa: BLE001
        pass

    # Prefer a production WSGI server. waitress works on Windows (gunicorn does
    # not). Falls back to the Flask dev server only if waitress isn't installed.
    if not debug:
        try:
            from waitress import serve
            logger.info("Serving with waitress (production WSGI server)")
            serve(app, host=host, port=port, threads=8)
            return
        except ImportError:
            logger.warning(
                "waitress not installed — falling back to the Flask dev server "
                "(NOT for production). Install with: pip install waitress"
            )
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_server()
