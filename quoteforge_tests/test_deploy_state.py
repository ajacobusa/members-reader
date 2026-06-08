"""Production-readiness tracker + hosting healthcheck."""
import pytest


def test_readiness_flags_local_hosting(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "PUBLIC_FILE_BASE_URL", "")
    monkeypatch.setattr(cfg, "PUBLIC_FILE_DIR", "")
    monkeypatch.delenv("GOOGLE_DRIVE_FOLDER_ID", raising=False)
    from quoteforge.automation.deployment_state import readiness
    s = readiness()
    host = next(i for i in s["items"] if i["name"] == "Print-file hosting")
    assert host["status"] == "todo"
    assert any(i["name"] == "TEST_MODE" for i in s["items"])


def test_public_dir_marks_hosting_ready(monkeypatch, tmp_path):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "PUBLIC_FILE_BASE_URL", "https://x/files")
    monkeypatch.setattr(cfg, "PUBLIC_FILE_DIR", str(tmp_path))
    from quoteforge.automation.file_host import active_backend
    b = active_backend()
    assert b["backend"] == "public_dir" and b["public"]


def test_write_migration_doc(tmp_path):
    from quoteforge.automation.deployment_state import write_migration_doc
    dest = tmp_path / "MIG.md"
    write_migration_doc(str(dest))
    txt = dest.read_text(encoding="utf-8")
    assert "Production Migration Tracker" in txt and "Production action" in txt


def test_healthcheck_includes_hosting():
    from quoteforge.automation.healthcheck import check_file_hosting
    c = check_file_hosting()
    assert c.name == "Print-file hosting" and c.status in ("OK", "WARN")


def test_deploy_status_command_registered():
    from quoteforge.admin import COMMANDS
    assert "deploy-status" in COMMANDS
