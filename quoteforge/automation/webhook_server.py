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
from quoteforge.etsy.order_processor import process_order, _log_order

app = Flask(__name__) if FLASK_AVAILABLE else None

WEBHOOK_LOG = OUTPUT_DIR / "webhook_log.json"


def _append_webhook_log(entry: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    if WEBHOOK_LOG.exists():
        try:
            entries = json.loads(WEBHOOK_LOG.read_text())
        except Exception:
            entries = []
    entries.append(entry)
    WEBHOOK_LOG.write_text(json.dumps(entries, indent=2))


def process_webhook_payload(payload: dict) -> dict:
    """Process an incoming webhook payload dict. Returns result dict.

    This function is testable without Flask running.
    """
    required = ["recipient_name", "occasion"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return {"status": "error", "message": f"Missing fields: {missing}"}

    try:
        result = process_order(
            recipient_name=payload.get("recipient_name", "Friend"),
            sender_name=payload.get("customer_name", "Anonymous"),
            relationship=payload.get("relationship", "To My Friend"),
            occasion=payload.get("occasion", "Special Occasion"),
            scenery=payload.get("scenery", "Mountains"),
            tone=payload.get("tone", "Inspirational & Motivational"),
            memory=payload.get("memory", ""),
            output_style=payload.get("output_style", "Personal Letter"),
            variations=1,
        )

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "order_id": payload.get("order_id", "unknown"),
            "customer": payload.get("customer_name", ""),
            "recipient": payload.get("recipient_name", ""),
            "occasion": payload.get("occasion", ""),
            "saved_to": str(result["saved_paths"][0]) if result["saved_paths"] else "",
            "status": "success",
        }
        _append_webhook_log(log_entry)

        return {
            "status": "success",
            "order_id": payload.get("order_id"),
            "message": f"Quote generated for {payload.get('recipient_name')}",
            "saved_to": str(result["saved_paths"][0]) if result["saved_paths"] else "",
            "variations_count": len(result["variations"]),
        }

    except Exception as exc:
        error_entry = {
            "timestamp": datetime.now().isoformat(),
            "order_id": payload.get("order_id", "unknown"),
            "status": "error",
            "error": str(exc),
        }
        _append_webhook_log(error_entry)
        return {"status": "error", "message": str(exc)}


if FLASK_AVAILABLE and app:
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "QuoteForge Webhook", "timestamp": datetime.now().isoformat()})

    @app.route("/order", methods=["POST"])
    def receive_order():
        payload = request.get_json(force=True, silent=True) or {}
        logger.info(f"Received order webhook: order_id={payload.get('order_id')}")
        result = process_webhook_payload(payload)
        status_code = 200 if result["status"] == "success" else 400
        return jsonify(result), status_code

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
