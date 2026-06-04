"""Tests for daily/weekly/monthly/yearly sales reports."""
from datetime import datetime, timedelta
from unittest.mock import patch

from quoteforge.etsy.reports import (
    period_window, period_report, format_report_text, PERIODS,
)
from quoteforge import admin


def test_all_periods_defined():
    assert PERIODS == ("daily", "weekly", "monthly", "yearly")


def test_period_windows_ordered():
    now = datetime(2026, 6, 15, 12, 0, 0)
    daily, _ = period_window("daily", now)
    weekly, _ = period_window("weekly", now)
    monthly, _ = period_window("monthly", now)
    yearly, _ = period_window("yearly", now)
    # Each wider window starts earlier (or equal)
    assert yearly <= monthly <= weekly <= daily <= now


def test_period_window_labels():
    now = datetime(2026, 6, 15)
    assert "2026" in period_window("yearly", now)[1]
    assert "June" in period_window("monthly", now)[1]


def test_period_window_invalid():
    import pytest
    with pytest.raises(ValueError):
        period_window("hourly")


def _seed(db, tmp_path, days_ago: int, status="shipped", price=30.0):
    from datetime import datetime, timedelta
    oid = f"O-{days_ago}-{status}"
    db.create_order({"order_id": oid, "recipient_name": "X", "occasion": "Y",
                     "sale_price": price, "gelato_cost": 11.0})
    # backdate created_at
    past = (datetime.now() - timedelta(days=days_ago)).isoformat()
    db.update_order(oid, status=status, created_at=past)
    return oid


def test_monthly_includes_recent_orders(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        _seed(db, tmp_path, days_ago=2)   # within all windows
        rep = period_report("monthly")
    assert rep["total_orders"] >= 1
    assert rep["financials"]["revenue"] >= 30.0


def test_weekly_excludes_old_orders(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        _seed(db, tmp_path, days_ago=2)    # in this week
        _seed(db, tmp_path, days_ago=20)   # older than a week
        weekly = period_report("weekly")
        yearly = period_report("yearly")
    assert weekly["total_orders"] == 1     # only the recent one
    assert yearly["total_orders"] == 2     # both within the year


def test_format_report_text_has_financials(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        _seed(db, tmp_path, days_ago=1)
        text = format_report_text(period_report("daily"))
    assert "DAILY SALES REPORT" in text
    assert "NET PROFIT" in text
    assert "Revenue" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_report_prints(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["report", "weekly"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "WEEKLY SALES REPORT" in out


def test_cli_report_invalid_period(capsys):
    rc = admin.main(["report", "hourly"])
    assert rc == 2
    assert "Usage" in capsys.readouterr().out


def test_cli_report_email_skips_without_creds(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.emailer.GMAIL_ADDRESS", ""), \
         patch("quoteforge.automation.emailer.GMAIL_APP_PASSWORD", ""):
        db.init_db()
        rc = admin.main(["report", "monthly", "email"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "skipped" in out.lower()
