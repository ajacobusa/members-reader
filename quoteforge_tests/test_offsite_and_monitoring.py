"""Tests for off-site Drive backup hook + optional error monitoring."""
from unittest.mock import patch

from quoteforge.automation import full_backup, monitoring


def _noop_git(args, runner=None):
    return 0, ""


def test_backup_skips_offsite_when_disabled(monkeypatch):
    monkeypatch.setattr("quoteforge.config.BACKUP_TO_DRIVE", False, raising=False)
    with patch.object(full_backup, "_git", _noop_git), \
         patch("quoteforge.db.database.backup_database", return_value=None), \
         patch("quoteforge.db.database.prune_old_backups", return_value=0):
        r = full_backup.run_full_backup(push=False, auto_commit=False)
    # offsite key not set when disabled; formatter shows "disabled"
    assert "Off-site : disabled" in full_backup.format_backup_text(r)


def test_backup_reports_offsite_when_enabled_but_unconfigured(monkeypatch):
    monkeypatch.setattr("quoteforge.config.BACKUP_TO_DRIVE", True, raising=False)
    with patch.object(full_backup, "_git", _noop_git), \
         patch("quoteforge.db.database.backup_database", return_value=None), \
         patch("quoteforge.db.database.prune_old_backups", return_value=0), \
         patch("quoteforge.automation.google_drive_client.is_configured",
               return_value=False):
        r = full_backup.run_full_backup(push=False, auto_commit=False)
    assert r["offsite"] == "skipped (Drive not configured)"


def test_monitoring_noop_without_dsn(monkeypatch):
    monkeypatch.setattr(monitoring, "_initialised", False, raising=False)
    monkeypatch.setattr("quoteforge.config.SENTRY_DSN", "", raising=False)
    assert monitoring.init_monitoring() is False
    monitoring.capture(ValueError("x"))   # must not raise
