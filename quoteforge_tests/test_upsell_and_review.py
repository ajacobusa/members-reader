"""Tests for upsell engine and review scheduler."""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from quoteforge.automation.upsell import (
    generate_upsell_message,
    generate_review_request,
    should_send_review,
    _base_canvas_upsell,
    _base_framed_upsell,
    _base_bundle_upsell,
    _base_review_request,
)


def _mock_claude(text: str):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    return mock_client


# ── Base template tests ──────────────────────────────────────────

def test_base_canvas_upsell_contains_name():
    msg = _base_canvas_upsell("Jennifer", "ScenicSoulPrints")
    assert "Jennifer" in msg
    assert "canvas" in msg.lower()


def test_base_framed_upsell_contains_name():
    msg = _base_framed_upsell("Jennifer", "ScenicSoulPrints")
    assert "Jennifer" in msg
    assert "frame" in msg.lower()


def test_base_bundle_upsell_contains_discount():
    msg = _base_bundle_upsell("Jennifer", "ScenicSoulPrints")
    assert "Jennifer" in msg
    assert "%" in msg or "discount" in msg.lower() or "set" in msg.lower()


def test_base_review_request_contains_names():
    msg = _base_review_request("Jennifer", "Emma", "ScenicSoulPrints")
    assert "Jennifer" in msg
    assert "Emma" in msg
    assert "review" in msg.lower()


# ── Upsell generation (no API key — uses base templates) ─────────

def test_generate_upsell_message_no_api_key():
    with patch("quoteforge.automation.upsell.ANTHROPIC_API_KEY", ""):
        result = generate_upsell_message("Jennifer", "Graduation", "poster")
    assert "canvas_message" in result
    assert "framed_message" in result
    assert "bundle_message" in result
    assert all(len(v) > 10 for v in result.values())


def test_generate_upsell_message_with_api():
    raw = "CANVAS: Upgrade to canvas for a stunning finish.\nFRAMED: Get it framed and ready to hang.\nBUNDLE: Save 15% on a set of 3 prints."
    with patch("quoteforge.automation.upsell.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.automation.upsell.anthropic.Anthropic", return_value=_mock_claude(raw)):
        result = generate_upsell_message("Jennifer", "Graduation")
    assert "canvas_message" in result
    assert len(result["canvas_message"]) > 5


# ── Review request ───────────────────────────────────────────────

def test_generate_review_request_no_api_key():
    with patch("quoteforge.automation.upsell.ANTHROPIC_API_KEY", ""):
        msg = generate_review_request("Jennifer", "Graduation", "Emma")
    assert isinstance(msg, str)
    assert len(msg) > 20


def test_generate_review_request_with_api():
    raw = "Hi Jennifer! I hope Emma loved her graduation print. A review would mean the world!"
    with patch("quoteforge.automation.upsell.ANTHROPIC_API_KEY", "test-key"), \
         patch("quoteforge.automation.upsell.anthropic.Anthropic", return_value=_mock_claude(raw)):
        msg = generate_review_request("Jennifer", "Graduation", "Emma")
    assert "Jennifer" in msg or len(msg) > 10


# ── Review timing ────────────────────────────────────────────────

def test_should_send_review_too_early():
    recent = datetime.now().isoformat()
    assert should_send_review(recent, delivery_days=7) is False


def test_should_send_review_ready():
    # Order created 25 days ago — should be ready (7 delivery + 14 review delay = 21 days)
    old_date = (datetime.now() - timedelta(days=25)).isoformat()
    assert should_send_review(old_date, delivery_days=7) is True


def test_should_send_review_invalid_date():
    assert should_send_review("not-a-date", delivery_days=7) is False


def test_should_send_review_exact_threshold():
    # Exactly at threshold: 7 + 14 = 21 days
    threshold_date = (datetime.now() - timedelta(days=21)).isoformat()
    result = should_send_review(threshold_date, delivery_days=7)
    assert isinstance(result, bool)


# ── Pipeline GUI import ───────────────────────────────────────────

def test_pipeline_tab_imports():
    from quoteforge.gui.pipeline_tab import PipelineTab, STAGE_LABELS, STATUS_COLORS
    assert len(STAGE_LABELS) == 7
    assert "received" in STATUS_COLORS
    assert "shipped" in STATUS_COLORS
    assert "error" in STATUS_COLORS


def test_pipeline_stage_labels_complete():
    from quoteforge.gui.pipeline_tab import STAGE_LABELS
    stage_nums = [s[0] for s in STAGE_LABELS]
    assert stage_nums == ["1", "2", "3", "4", "5", "6", "7"]


# ── Full app imports (7 tabs) ─────────────────────────────────────

def test_all_seven_tabs_import():
    from quoteforge.main import main
    from quoteforge.gui.pipeline_tab import PipelineTab
    from quoteforge.gui.profit_tab import ProfitTab
    from quoteforge.gui.prompts_tab import PromptsTab
    from quoteforge.gui.order_tab import OrderTab
    from quoteforge.gui.catalog_tab import CatalogTab
    from quoteforge.gui.personal_tab import PersonalTab
    assert all([PipelineTab, ProfitTab, PromptsTab, OrderTab, CatalogTab, PersonalTab])
