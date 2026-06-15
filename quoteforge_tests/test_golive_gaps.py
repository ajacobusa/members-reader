"""Tests for the three go-live gap fixes:
1. Gelato webhook signature verification + callback handling
2. Per-size artwork rendering
3. Gelato product UID mapping verification
"""
from unittest.mock import patch

import pytest

from quoteforge.automation.webhook_security import (
    compute_signature, verify_gelato_signature,
)
from quoteforge.automation.webhook_server import process_gelato_callback
from quoteforge.etsy.gelato_catalog import (
    dimensions_for, get_product, verify_catalog_mappings,
)


# ── Gap 1: Gelato webhook signature ──────────────────────────────

def test_gelato_signature_accepts_valid():
    body = b'{"orderReferenceId":"X","status":"shipped"}'
    sig = compute_signature(body, "gsecret")
    assert verify_gelato_signature(body, sig, secret="gsecret") is True


def test_gelato_signature_rejects_tampered():
    body = b'{"orderReferenceId":"X"}'
    sig = compute_signature(body, "gsecret")
    assert verify_gelato_signature(b'{"evil":true}', sig, secret="gsecret") is False


def test_gelato_signature_skipped_without_secret():
    # Dev parity: no secret configured -> verification disabled.
    assert verify_gelato_signature(b"{}", "", secret="") is True


def test_gelato_callback_updates_status_and_tracking(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "G1", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        res = process_gelato_callback({"orderReferenceId": "G1",
                                       "status": "shipped",
                                       "trackingCode": "1Z999"})
        order = db.get_order("G1")
    assert res["status"] == "ok"
    assert order["status"] == "shipped"
    assert order["tracking_number"] == "1Z999"


def test_gelato_canceled_normalizes_to_cancelled_spelling(tmp_path):
    # REGRESSION: Gelato sends "canceled" (one L); every downstream consumer
    # checks "cancelled" (two Ls). The webhook must normalize so a cancelled
    # order is recognized (terminal for the tracker, counted in metrics, no
    # review request fired).
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "G2", "recipient_name": "E", "occasion": "G"})
        process_gelato_callback({"orderReferenceId": "G2", "status": "canceled"})
        order = db.get_order("G2")
    assert order["status"] == "cancelled"


def test_gelato_passed_maps_to_in_production(tmp_path):
    # REGRESSION: Gelato "passed" must map to a status consumers recognize
    # (in_production), not an orphaned "fulfillment_accepted" that order_monitor
    # and financial reports never read.
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "G3", "recipient_name": "E", "occasion": "G"})
        process_gelato_callback({"orderReferenceId": "G3", "status": "passed"})
        order = db.get_order("G3")
    assert order["status"] == "in_production"


def test_gelato_callback_ignores_unknown_reference(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        res = process_gelato_callback({"orderReferenceId": "NOPE",
                                       "status": "shipped"})
    assert res["status"] == "ignored"


# ── Gap 2: Per-size rendering ────────────────────────────────────

def test_dimensions_resolve_by_size():
    assert dimensions_for("11x14 in") == (3300, 4200)
    assert dimensions_for("8x10") == (2400, 3000)


def test_dimensions_resolve_by_product_id_and_sku():
    assert dimensions_for("poster_8x10") == (2400, 3000)
    assert get_product("GEL-POSTER-11X14-STD").size == "11x14 in"


def test_dimensions_default_when_unknown():
    assert dimensions_for("nonsense") == (5400, 7200)  # 18x24 fallback


def test_pipeline_renders_at_ordered_size(tmp_path):
    from PIL import Image
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "TEST_MODE", False), \
         patch.object(po, "GENERATE_ROOM_MOCKUP", False), \
         patch.object(po, "CUSTOMER_PROOF_APPROVAL", False), \
         patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", True), \
         patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
               return_value=None):
        db.init_db()
        po.run_full_pipeline({"order_id": "SZ", "recipient_name": "Emma",
                              "occasion": "Graduation", "sender_name": "Mom",
                              "relationship": "Daughter",
                              "product_size": "11x14 in"}, skip_proof=True)
        art = tmp_path / "pipeline" / "SZ" / "artwork.png"
        with Image.open(art) as im:
            assert im.size == (3300, 4200)  # rendered at the ordered 11x14, not 18x24


# ── Gap 3: Gelato UID mapping verification ───────────────────────

def test_seed_catalog_flagged_as_placeholders():
    m = verify_catalog_mappings()
    # The shipped catalog uses GEL-* placeholders until the owner fills real UIDs.
    assert m["placeholder_count"] > 0
    assert m["all_real"] is False
    assert m["configured"] + m["placeholder_count"] == m["total"]


def test_real_uids_pass(monkeypatch):
    import quoteforge.etsy.gelato_catalog as gc
    for p in gc.GELATO_CATALOG:
        monkeypatch.setattr(p, "gelato_sku", "posters_300x400-mm_200-gsm_4-0", raising=False)
    m = gc.verify_catalog_mappings()
    assert m["all_real"] is True
    assert m["placeholder_count"] == 0
