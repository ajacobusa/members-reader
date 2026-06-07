"""Tests for the analytics block in the daily report."""


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def test_analytics_summary_shape(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    from quoteforge.automation.analytics_report import (analytics_summary,
                                                        format_analytics_text)
    a = analytics_summary()
    assert "etsy" in a and "ga" in a and "clarity" in a
    txt = format_analytics_text(a)
    assert "ANALYTICS" in txt and "Etsy" in txt and "Google Analytics" in txt \
        and "Microsoft Clarity" in txt


def test_analytics_status_reflects_config(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    monkeypatch.setattr("quoteforge.config.GA_MEASUREMENT_ID", "G-XYZ", raising=False)
    monkeypatch.setattr("quoteforge.config.CLARITY_PROJECT_ID", "", raising=False)
    from quoteforge.automation.analytics_report import analytics_summary, format_analytics_text
    txt = format_analytics_text(analytics_summary())
    assert "G-XYZ" in txt and "not set" in txt   # GA active, Clarity not set


def test_briefing_includes_analytics(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    from quoteforge.automation.briefing import morning_briefing, format_briefing_text
    b = morning_briefing()
    assert "analytics" in b
    assert "ANALYTICS" in format_briefing_text(b)


def test_analytics_command_registered():
    from quoteforge import admin
    assert "analytics" in admin.COMMANDS
