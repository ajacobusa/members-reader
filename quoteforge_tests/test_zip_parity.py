"""Tests for the gap-fill features added to reach parity with the
etsy_gelato_automation_pipeline.zip reference: TEST_MODE, webhook signing,
new DB tables, production message, and the Streamlit monitor."""
from unittest.mock import patch

from quoteforge.automation.webhook_security import (
    compute_signature, verify_signature,
)
from quoteforge.etsy.customer_messages import BASE_TEMPLATES, MESSAGE_TYPES
from quoteforge.db.database import (
    init_db, create_order,
    save_customer_message, get_customer_messages, mark_message_sent,
    save_upsell, get_upsells,
    save_review, get_pending_reviews, mark_review_sent,
)
from quoteforge.automation.gelato_api import create_gelato_order


# ── TEST_MODE config ─────────────────────────────────────────────

def test_test_mode_default_is_true():
    import quoteforge.config as cfg
    # Default ships as True for safety
    assert isinstance(cfg.TEST_MODE, bool)


def test_gelato_test_mode_returns_mock():
    with patch("quoteforge.automation.gelato_api.TEST_MODE", True):
        result = create_gelato_order(
            order_id="QF-001",
            recipient={"name": "Emma", "country": "US"},
            artwork_url="https://example.com/art.png",
            product_uid="poster_18x24",
        )
    assert result["test_mode"] is True
    assert result["gelato_order_id"] == "TEST-GELATO-QF-001"
    assert result["tracking_number"] == "TEST-TRACKING-123"


# ── Webhook signature verification ───────────────────────────────

def test_compute_signature_is_deterministic():
    payload = b'{"order_id":"123"}'
    sig1 = compute_signature(payload, "secret")
    sig2 = compute_signature(payload, "secret")
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA-256 hex


def test_verify_signature_valid():
    payload = b'{"order_id":"123"}'
    sig = compute_signature(payload, "my-secret")
    assert verify_signature(payload, sig, "my-secret") is True


def test_verify_signature_invalid():
    payload = b'{"order_id":"123"}'
    assert verify_signature(payload, "wronghash", "my-secret") is False


def test_verify_signature_skipped_when_no_secret():
    # No secret configured → verification disabled (dev mode).
    # Patch the module constant so an ambient .env secret can't interfere.
    with patch("quoteforge.automation.webhook_security.ETSY_WEBHOOK_SECRET", ""):
        payload = b'{"order_id":"123"}'
        assert verify_signature(payload, "", "") is True


def test_verify_signature_rejects_missing_sig_when_secret_set():
    payload = b'{"order_id":"123"}'
    assert verify_signature(payload, "", "my-secret") is False


# ── New customer message type ────────────────────────────────────

def test_in_production_message_exists():
    assert "In Production" in BASE_TEMPLATES
    assert "production" in BASE_TEMPLATES["In Production"].lower()


def test_five_message_types_now():
    assert len(MESSAGE_TYPES) == 6      # + "Order Delivered" (buyer delivery confirmation)


# ── New DB tables: customer_messages, upsells, reviews ───────────

def test_customer_message_persistence(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid = create_order({"recipient_name": "Emma", "occasion": "Graduation"})
        mid = save_customer_message(oid, "Order Received", "Thank you!", sent=False)
        msgs = get_customer_messages(oid)
        assert len(msgs) == 1
        assert msgs[0]["message_type"] == "Order Received"
        assert msgs[0]["sent"] == 0
        mark_message_sent(mid)
        assert get_customer_messages(oid)[0]["sent"] == 1


def test_upsell_persistence(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid = create_order({"recipient_name": "Bob", "occasion": "Birthday"})
        save_upsell(oid, "canvas", "Upgrade to canvas for $15 more!")
        upsells = get_upsells(oid)
        assert len(upsells) == 1
        assert upsells[0]["offer_type"] == "canvas"


def test_review_persistence(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid = create_order({"recipient_name": "Cara", "occasion": "Wedding"})
        rid = save_review(oid, "Please leave a review!", scheduled_for="2026-07-01")
        pending = get_pending_reviews()
        assert any(r["order_id"] == oid for r in pending)
        mark_review_sent(rid)
        assert all(r["id"] != rid for r in get_pending_reviews())


# ── gelato_product_uid column migration ──────────────────────────

def test_order_has_gelato_product_uid_column(tmp_path):
    from quoteforge.db.database import update_order, get_order
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid = create_order({"recipient_name": "Dee", "occasion": "Anniversary"})
        update_order(oid, gelato_product_uid="poster_18x24_uid")
        order = get_order(oid)
        assert order["gelato_product_uid"] == "poster_18x24_uid"


# ── Streamlit monitor imports without crashing ───────────────────

def test_web_monitor_imports():
    # streamlit/pandas may not be installed; module must still import
    import quoteforge.web_monitor as wm
    assert hasattr(wm, "render")
    assert hasattr(wm, "STAGE_ORDER")
