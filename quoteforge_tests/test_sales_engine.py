"""Tests for the automated sales & upsell engine."""
from datetime import datetime, timedelta
from unittest.mock import patch

from quoteforge.etsy.sales_engine import (
    best_sellers, upsell_actions, winback_actions, review_actions,
    sales_actions_digest, format_digest_text, NEXT_ORDER_COUPON,
)
from quoteforge import admin


def test_best_sellers_ranks_occasions():
    orders = [
        {"occasion": "Graduation", "relationship": "Daughter", "status": "shipped"},
        {"occasion": "Graduation", "relationship": "Son", "status": "shipped"},
        {"occasion": "Wedding", "relationship": "Daughter", "status": "in_production"},
        {"occasion": "Pending", "relationship": "X", "status": "received"},  # excluded
    ]
    bs = best_sellers(orders)
    top = dict(bs["top_occasions"])
    assert top["Graduation"] == 2
    assert "Pending" not in top  # non-billable excluded


def test_upsell_actions_targets_fulfilled_unupsold():
    orders = [
        {"order_id": "A", "status": "shipped", "upsell_sent": 0, "sender_name": "Mom"},
        {"order_id": "B", "status": "shipped", "upsell_sent": 1},  # already upsold
        {"order_id": "C", "status": "received", "upsell_sent": 0},  # not fulfilled
    ]
    acts = upsell_actions(orders)
    ids = [a["order_id"] for a in acts]
    assert ids == ["A"]
    assert acts[0]["type"] == "upsell"


def test_winback_targets_year_old_recurring():
    now = datetime(2026, 6, 1)
    year_ago = (now - timedelta(days=350)).isoformat()
    recent = (now - timedelta(days=10)).isoformat()
    orders = [
        {"order_id": "ANNIV", "occasion": "Anniversary", "created_at": year_ago,
         "sender_name": "Bob"},
        {"order_id": "BDAY-RECENT", "occasion": "Birthday", "created_at": recent},
        {"order_id": "GRAD", "occasion": "Graduation",  # not recurring
         "created_at": year_ago},
    ]
    acts = winback_actions(orders, now)
    ids = [a["order_id"] for a in acts]
    assert "ANNIV" in ids           # ~1 year old + recurring → win-back
    assert "BDAY-RECENT" not in ids  # too recent
    assert "GRAD" not in ids         # graduation doesn't recur
    assert NEXT_ORDER_COUPON in acts[0]["suggested"]


def test_review_actions_due(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "R-1", "recipient_name": "X", "occasion": "Y"})
        past = (datetime.now() - timedelta(days=1)).isoformat()
        db.save_review("R-1", "Please review!", scheduled_for=past)  # due
        future = (datetime.now() + timedelta(days=30)).isoformat()
        db.save_review("R-1", "Later", scheduled_for=future)         # not due
        acts = review_actions()
    assert len(acts) == 1
    assert acts[0]["type"] == "review"


def test_sales_digest_structure(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        oid = db.create_order({"order_id": "S-1", "recipient_name": "X",
                               "occasion": "Anniversary", "sender_name": "Mom"})
        db.update_order(oid, status="shipped")
        digest = sales_actions_digest()
    assert "upsells" in digest
    assert "reviews" in digest
    assert "winbacks" in digest
    assert "best_sellers" in digest
    assert digest["next_order_coupon"] == NEXT_ORDER_COUPON
    # The shipped, un-upsold order is an upsell action
    assert any(a["order_id"] == "S-1" for a in digest["upsells"])


def test_format_digest_text():
    digest = {"upsells": [], "reviews": [], "winbacks": [],
              "best_sellers": {"top_occasions": [], "top_relationships": []},
              "total_actions": 0, "next_order_coupon": "X"}
    text = format_digest_text(digest)
    assert "AUTOMATED SALES ACTIONS" in text
    assert "BEST SELLERS" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_sales(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["sales"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "AUTOMATED SALES ACTIONS" in out


def test_daily_report_includes_sales_actions(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation.emailer import build_report_html
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        _, body = build_report_html()
    assert "Sales Actions to Send Today" in body
    assert "Upsells" in body
