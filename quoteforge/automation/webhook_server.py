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


def process_webhook_payload(payload: dict) -> dict:
    """Process an incoming Etsy webhook payload through the full pipeline.

    - Idempotent: a retried delivery for the same Etsy order is detected and
      skipped (prevents duplicate quotes and duplicate Gelato charges).
    - Routes through run_full_pipeline so the order lands in the database and
      appears in the monitor with full per-stage logging.

    This function is testable without Flask running.
    """
    required = ["recipient_name", "occasion"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return {"status": "error", "message": f"Missing fields: {missing}"}

    etsy_order_id = str(payload.get("order_id") or payload.get("etsy_order_id") or "")

    # ── Idempotency guard ───────────────────────────────────────
    if etsy_order_id:
        from quoteforge.db.database import init_db, get_order_by_etsy_id
        init_db()
        existing = get_order_by_etsy_id(etsy_order_id)
        if existing:
            logger.info(f"Duplicate webhook for Etsy order {etsy_order_id} — skipping")
            _append_webhook_log({
                "timestamp": datetime.now().isoformat(),
                "order_id": etsy_order_id,
                "status": "duplicate_skipped",
            })
            return {
                "status": "duplicate",
                "order_id": etsy_order_id,
                "message": "Order already processed — skipped to avoid duplicate fulfillment",
                "internal_order_id": existing["order_id"],
            }

    try:
        from quoteforge.automation.pipeline_orchestrator import run_full_pipeline

        order_data = {
            "etsy_order_id": etsy_order_id,
            "customer_name": payload.get("customer_name", ""),
            "customer_email": payload.get("customer_email", ""),
            "recipient_name": payload.get("recipient_name", "Friend"),
            "sender_name": payload.get("customer_name", "Anonymous"),
            "relationship": payload.get("relationship", "To My Friend"),
            "occasion": payload.get("occasion", "Special Occasion"),
            "scenery": payload.get("scenery", "Mountains"),
            "tone": payload.get("tone", "Inspirational & Motivational"),
            "memory": payload.get("memory", ""),
            "output_style": payload.get("output_style", "Personal Letter"),
            # Real sale price from Etsy (Make.com maps the order total). Accept
            # several common field names; None → financials fall back to default.
            "sale_price": _parse_money(
                payload.get("sale_price") or payload.get("price")
                or payload.get("total") or payload.get("order_total")
                or payload.get("grandtotal")
            ),
            "gelato_cost": _parse_money(payload.get("gelato_cost")),
        }

        # Default config stops at the proof stage for manual review — exactly
        # the right behavior for personalized orders.
        result = run_full_pipeline(order_data)

        _append_webhook_log({
            "timestamp": datetime.now().isoformat(),
            "order_id": etsy_order_id,
            "internal_order_id": result.get("order_id", ""),
            "recipient": payload.get("recipient_name", ""),
            "occasion": payload.get("occasion", ""),
            "status": result.get("status", "processed"),
        })

        return {
            "status": "success",
            "order_id": etsy_order_id,
            "internal_order_id": result.get("order_id", ""),
            "pipeline_status": result.get("status", ""),
            "message": f"Order processed for {payload.get('recipient_name')}",
        }

    except Exception as exc:
        _append_webhook_log({
            "timestamp": datetime.now().isoformat(),
            "order_id": etsy_order_id,
            "status": "error",
            "error": str(exc),
        })
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
        prune_old_backups(keep=14)
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


def run_server(host: str = "0.0.0.0", port: int = 5050, debug: bool = False) -> None:
    if not FLASK_AVAILABLE:
        print("Flask not installed. Run: pip install flask")
        return
    logger.info(f"QuoteForge Webhook Server starting on {host}:{port}")
    logger.info("Zapier/Make.com: POST to http://YOUR-IP:5050/order")

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
