"""Tests for the full 7-stage pipeline infrastructure."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from quoteforge.db.database import (
    init_db, create_order, get_order, update_order,
    get_orders_by_status, get_order_stats, log_pipeline_stage,
    get_pipeline_log, upsert_product, get_products_by_category,
    upsert_template, get_templates_by_scenery,
)
from quoteforge.automation.canva_api import (
    is_configured as canva_configured,
    get_canva_setup_guide,
)
from quoteforge.automation.google_drive_client import (
    is_configured as drive_configured,
    get_google_drive_setup,
)
from quoteforge.automation.airtable_client import (
    get_airtable_setup_instructions, _is_configured as airtable_configured,
)
from quoteforge.automation.gelato_api import get_gelato_api_setup
from quoteforge.automation.pipeline_orchestrator import STAGES, STATUS_MAP


# ── Database tests ───────────────────────────────────────────────

def test_db_init_creates_tables(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
    assert (tmp_path / "test.db").exists()


def test_create_and_get_order(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid = create_order({
            "recipient_name": "Emma",
            "occasion": "Graduation",
            "sender_name": "Mom",
            "relationship": "To My Daughter",
        })
        order = get_order(oid)
    assert order is not None
    assert order["recipient_name"] == "Emma"
    assert order["occasion"] == "Graduation"
    assert order["status"] == "received"


def test_update_order_changes_status(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid = create_order({"recipient_name": "Bob", "occasion": "Birthday"})
        update_order(oid, status="quote_generated", generated_quote="You are amazing.")
        order = get_order(oid)
    assert order["status"] == "quote_generated"
    assert order["generated_quote"] == "You are amazing."


def test_get_orders_by_status(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        create_order({"recipient_name": "A", "occasion": "X"})
        create_order({"recipient_name": "B", "occasion": "Y"})
        received = get_orders_by_status("received")
    assert len(received) == 2
    assert all(o["status"] == "received" for o in received)


def test_order_stats_aggregate(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid1 = create_order({"recipient_name": "A", "occasion": "X"})
        oid2 = create_order({"recipient_name": "B", "occasion": "Y"})
        update_order(oid2, status="shipped")
        stats = get_order_stats()
    assert stats["total"] == 2
    assert stats["by_status"]["received"] == 1
    assert stats["by_status"]["shipped"] == 1


def test_pipeline_log_records_stages(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        oid = create_order({"recipient_name": "C", "occasion": "Z"})
        log_pipeline_stage(oid, "quote_generation", "success", "130 chars")
        log_pipeline_stage(oid, "artwork_generation", "success", "PNG rendered")
        logs = get_pipeline_log(oid)
    assert len(logs) == 2
    assert logs[0]["stage"] == "quote_generation"
    assert logs[1]["stage"] == "artwork_generation"


def test_upsert_and_get_product(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        upsert_product({
            "product_id": "poster_18x24",
            "category": "Daughter Gifts",
            "gelato_sku": "poster_18x24",
            "title": "Personalized Daughter Gift Poster",
            "price_usd": 29.99,
            "gelato_cost_usd": 11.00,
            "product_type": "poster",
            "size": "18x24 in",
        })
        products = get_products_by_category("Daughter Gifts")
    assert len(products) == 1
    assert products[0]["price_usd"] == 29.99


def test_upsert_and_get_template(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "test.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        init_db()
        upsert_template({
            "template_id": "tmpl_mountain_001",
            "theme": "Mountain Sunrise",
            "scenery_type": "Mountains",
            "category": "Motivation & Mindset",
        })
        templates = get_templates_by_scenery("Mountains")
    assert len(templates) == 1
    assert templates[0]["theme"] == "Mountain Sunrise"


# ── Pipeline stages ──────────────────────────────────────────────

def test_pipeline_has_seven_stages():
    assert len(STAGES) == 7


def test_status_map_covers_all_stages():
    for stage in STAGES:
        assert stage in STATUS_MAP, f"Stage '{stage}' not in STATUS_MAP"


def test_stage_order_is_correct():
    assert STAGES[0] == "order_intake"
    assert STAGES[1] == "quote_generation"
    assert STAGES[2] == "artwork_generation"
    assert STAGES[-1] == "followup"


# ── External API clients (unconfigured = graceful skip) ──────────

def test_canva_not_configured_by_default():
    assert canva_configured() is False


def test_canva_setup_guide_returns_text():
    guide = get_canva_setup_guide()
    assert "CANVA" in guide.upper()
    assert len(guide) > 100


def test_drive_not_configured_by_default():
    assert drive_configured() is False


def test_drive_setup_guide_returns_text():
    guide = get_google_drive_setup()
    assert "GOOGLE DRIVE" in guide.upper()


def test_airtable_not_configured_by_default():
    assert airtable_configured() is False


def test_airtable_setup_instructions_return_text():
    instructions = get_airtable_setup_instructions()
    assert "AIRTABLE" in instructions.upper()
    assert "Orders" in instructions


def test_gelato_api_setup_guide_returns_text():
    guide = get_gelato_api_setup()
    assert "GELATO" in guide.upper()


# ── Pipeline orchestrator imports ────────────────────────────────

def test_pipeline_orchestrator_imports():
    from quoteforge.automation.pipeline_orchestrator import (
        run_full_pipeline, resume_after_proof_approval, get_pipeline_summary,
    )
    assert callable(run_full_pipeline)
    assert callable(resume_after_proof_approval)
    assert callable(get_pipeline_summary)
