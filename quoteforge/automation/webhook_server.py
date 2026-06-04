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


if FLASK_AVAILABLE and app:
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "QuoteForge Webhook", "timestamp": datetime.now().isoformat()})

    @app.route("/order", methods=["POST"])
    def receive_order():
        from quoteforge.automation.webhook_security import verify_signature
        raw_body = request.get_data()
        signature = request.headers.get("X-Webhook-Signature", "")
        if not verify_signature(raw_body, signature):
            logger.warning("Rejected webhook — invalid signature")
            return jsonify({"status": "error", "message": "Invalid signature"}), 401
        payload = request.get_json(force=True, silent=True) or {}
        logger.info(f"Received order webhook: order_id={payload.get('order_id')}")
        result = process_webhook_payload(payload)
        # 2xx for success AND duplicate (both are "done" — don't make Make.com retry).
        # 4xx only for genuine errors so the sender can alert/retry.
        status_code = 200 if result["status"] in ("success", "duplicate") else 400
        return jsonify(result), status_code

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
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_server()
