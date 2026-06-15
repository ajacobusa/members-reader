"""End-to-end pipeline test — runs a complete fake order through all 7 stages
in TEST_MODE, asserting each of the user's go-live checkpoints.

This is the automated version of the manual "run one fake order" verification.
"""
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def isolated_pipeline(tmp_path):
    """Patch DB + output dirs to a temp location for an isolated run."""
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import init_db
        init_db()
        yield tmp_path


FAKE_ORDER = {
    "order_id": "E2E-TEST-001",
    "etsy_order_id": "ETSY-12345",
    "customer_name": "Jennifer Smith",
    "customer_email": "jen@example.com",
    "recipient_name": "Emma",
    "sender_name": "Mom",
    "relationship": "To My Daughter",
    "occasion": "Graduation",
    "scenery": "Mountains",
    "tone": "Inspirational & Motivational",
    "memory": "She worked so hard and never gave up.",
    "output_style": "Personal Letter",
}


def _run(tmp_path):
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline, STAGES
    stages_fired = []
    run_full_pipeline(
        FAKE_ORDER,
        on_stage=lambda stage, msg: stages_fired.append(stage),
        skip_proof=True,
        gelato_product_uid="poster_18x24_uid",
        recipient_address={"name": "Emma", "address": "1 Main St",
                           "city": "Atlanta", "state": "GA", "postCode": "30301",
                           "country": "US", "email": "e@x.com"},
    )
    return stages_fired, STAGES


def test_order_logs_to_db(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_order
    order = get_order("E2E-TEST-001")
    assert order is not None
    assert order["etsy_order_id"] == "ETSY-12345"


def test_quote_generated_in_test_mode(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_order
    order = get_order("E2E-TEST-001")
    assert order["generated_quote"]
    assert "Emma" in order["generated_quote"]


def test_artwork_png_physically_created(isolated_pipeline):
    _run(isolated_pipeline)
    png = isolated_pipeline / "pipeline" / "E2E-TEST-001" / "artwork.png"
    assert png.exists()
    assert png.stat().st_size > 1000  # real PNG, not empty


def test_gelato_mock_order_created(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_order
    order = get_order("E2E-TEST-001")
    assert order["gelato_order_id"] == "TEST-GELATO-E2E-TEST-001"


def test_routing_failure_marks_order_error_not_shipped(isolated_pipeline):
    """REGRESSION: when vendor routing fails, the order must end 'error' (so the
    scheduled healthcheck/order-monitor alert the owner), NOT silently proceed
    through follow-up to a 'shipped' status as if it had been fulfilled."""
    from quoteforge.automation.pipeline_orchestrator import run_full_pipeline
    from quoteforge.db.database import get_order, get_customer_messages
    with patch("quoteforge.fulfillment.router.route_order",
               return_value={"status": "error", "vendor": "gelato", "id": "",
                             "detail": "vendor down"}):
        run_full_pipeline(
            FAKE_ORDER, skip_proof=True, gelato_product_uid="poster_18x24_uid",
            recipient_address={"name": "Emma", "address": "1 Main St",
                               "city": "Atlanta", "state": "GA",
                               "postCode": "30301", "country": "US"})
    order = get_order("E2E-TEST-001")
    assert order["status"] == "error"          # surfaced, not "shipped"


def test_customer_messages_created(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_customer_messages
    msgs = get_customer_messages("E2E-TEST-001")
    assert len(msgs) >= 5  # all lifecycle messages


def test_upsell_offers_created(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_upsells
    upsells = get_upsells("E2E-TEST-001")
    assert len(upsells) == 3  # canvas, framed, bundle


def test_review_request_scheduled(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_pending_reviews
    reviews = get_pending_reviews()
    assert any(r["order_id"] == "E2E-TEST-001" for r in reviews)


def test_all_seven_stages_fired(isolated_pipeline):
    stages_fired, STAGES = _run(isolated_pipeline)
    fired_unique = [s for s in STAGES if s in stages_fired]
    assert len(fired_unique) == 7, f"Only fired: {fired_unique}"


def test_pipeline_log_has_all_stages(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_pipeline_log
    logs = get_pipeline_log("E2E-TEST-001")
    logged_stages = {log["stage"] for log in logs}
    for stage in ["order_intake", "quote_generation", "artwork_generation",
                  "drive_upload", "proof", "gelato_order", "followup"]:
        assert stage in logged_stages, f"Stage '{stage}' not logged"


def test_final_status_is_shipped(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_order
    order = get_order("E2E-TEST-001")
    assert order["status"] == "shipped"


def test_monitor_can_read_orders(isolated_pipeline):
    _run(isolated_pipeline)
    from quoteforge.db.database import get_all_orders, get_order_stats
    assert len(get_all_orders()) == 1
    stats = get_order_stats()
    assert stats["total"] == 1
    assert stats["by_status"].get("shipped") == 1
