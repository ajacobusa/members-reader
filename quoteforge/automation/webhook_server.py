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
    "passed": "fulfillment_accepted",
    "in_production": "in_production",
    "printed": "in_production",
    "shipped": "shipped",
    "delivered": "delivered",
    "canceled": "canceled",
    "cancelled": "canceled",
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
