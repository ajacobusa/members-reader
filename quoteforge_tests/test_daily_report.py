"""Tests for the daily report email + demand-based tier recommendations."""
from unittest.mock import patch, MagicMock

from quoteforge.etsy.tier_advisor import recommend_tiers, TIER_LADDER
from quoteforge.automation.emailer import build_report_html, send_daily_report
from quoteforge import admin


# ── Tier advisor ─────────────────────────────────────────────────

def test_low_volume_no_recommendations():
    # 50 orders, local renderer (free) → nothing to upgrade
    recs = recommend_tiers(monthly_orders=50, renderer="local")
    assert recs == []


def test_bannerbear_only_when_used():
    # High volume but on local renderer → no Bannerbear recs
    recs = recommend_tiers(monthly_orders=900, renderer="local")
    assert all(r["service"] != "Bannerbear" for r in recs)


def test_bannerbear_approaching_limit():
    # 850 orders ≈ 85% of Automate's 1000 → APPROACHING warning
    recs = recommend_tiers(monthly_orders=850, renderer="bannerbear")
    bb = [r for r in recs if r["service"] == "Bannerbear" and r["current_plan"] == "Automate"]
    assert bb and bb[0]["status"] == "APPROACHING"


def test_bannerbear_over_limit():
    recs = recommend_tiers(monthly_orders=1500, renderer="bannerbear")
    # The Automate plan (1000 limit) is exceeded → recommends Scale
    automate = [r for r in recs if r["service"] == "Bannerbear"
                and r["current_plan"] == "Automate"]
    assert automate
    assert automate[0]["status"] == "OVER_LIMIT"
    assert automate[0]["recommended_plan"] == "Scale"


def test_make_com_scales_with_orders():
    # Make.com ops ≈ orders*4; 300 orders → 1200 ops = at Starter limit
    recs = recommend_tiers(monthly_orders=300, renderer="local")
    assert any(r["service"] == "Make.com" for r in recs)


# ── Report HTML ──────────────────────────────────────────────────

def test_hold_validation_surfaced_in_needs_attention(tmp_path):
    # REGRESSION: hold_validation is a money-gate failure that previously had no
    # owner-facing surfacing. It must appear in the daily report's attention list.
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "HV-1", "recipient_name": "E", "occasion": "G"})
        db.update_order("HV-1", status="hold_validation")
        report = db.daily_order_report()
    assert any(o["order_id"] == "HV-1" for o in report["needs_attention"])


def test_build_report_html_structure(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "R-1", "recipient_name": "Emma", "occasion": "Graduation"})
        subject, body = build_report_html()
    assert "QuoteForge Daily Report" in subject
    assert "new orders today" in subject.lower()  # scoped to today, not all-time
    assert "Daily Sales Report" in body
    assert "New Orders Today" in body
    assert "Today's Financials" in body
    assert "All-time net profit" in body


def test_build_report_escapes_html(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "X", "recipient_name": "<script>", "occasion": "Y"})
        db.update_order("X", status="error")
        _, body = build_report_html()
    assert "<script>" not in body  # escaped
    assert "&lt;script&gt;" in body


# ── Emailer ──────────────────────────────────────────────────────

def test_send_report_skips_without_credentials():
    with patch("quoteforge.automation.emailer.GMAIL_ADDRESS", ""), \
         patch("quoteforge.automation.emailer.GMAIL_APP_PASSWORD", ""):
        result = send_daily_report()
    assert result["status"] == "skipped"


def test_send_report_uses_smtp(tmp_path):
    import quoteforge.db.database as db
    fake_smtp = MagicMock()
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_smtp)
    fake_ctx.__exit__ = MagicMock(return_value=False)
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.emailer.GMAIL_ADDRESS", "shop@gmail.com"), \
         patch("quoteforge.automation.emailer.GMAIL_APP_PASSWORD", "app-pass"), \
         patch("quoteforge.automation.emailer.REPORT_RECIPIENT", "ajacobusa@gmail.com"), \
         patch("quoteforge.automation.emailer.smtplib.SMTP_SSL", return_value=fake_ctx):
        db.init_db()
        result = send_daily_report()
    assert result["status"] == "sent"
    assert result["to"] == "ajacobusa@gmail.com"
    fake_smtp.login.assert_called_once_with("shop@gmail.com", "app-pass")
    fake_smtp.sendmail.assert_called_once()


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_email_report_skips_cleanly(capsys):
    with patch("quoteforge.automation.emailer.GMAIL_ADDRESS", ""), \
         patch("quoteforge.automation.emailer.GMAIL_APP_PASSWORD", ""):
        rc = admin.main(["email-report"])
    assert rc == 1
    assert "not sent" in capsys.readouterr().out.lower()
