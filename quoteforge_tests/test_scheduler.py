"""Tests for the scheduled-jobs installer (single source of truth)."""
from quoteforge.automation import scheduler
from quoteforge.automation.scheduler import (
    SCHEDULED_JOBS, EXPECTED_TASK_NAMES, build_create_command,
    build_delete_command, install_schedule, format_install_text,
)
from quoteforge import admin


def test_all_jobs_defined_with_unique_names():
    assert len(SCHEDULED_JOBS) == 50   # + ...code-audit, runtime-health, shipping-rate-review
    assert "QuoteForge Shipping Rate Review" in EXPECTED_TASK_NAMES
    assert "QuoteForge Runtime Health" in EXPECTED_TASK_NAMES
    assert "QuoteForge Code Audit Sweep" in EXPECTED_TASK_NAMES
    assert "QuoteForge Wave Books Review" in EXPECTED_TASK_NAMES
    assert "QuoteForge Wave Daily Transactions" in EXPECTED_TASK_NAMES
    assert "QuoteForge Fulfillment Retry" in EXPECTED_TASK_NAMES
    assert "QuoteForge Customer Notifications" in EXPECTED_TASK_NAMES
    assert "QuoteForge Daily QA" in EXPECTED_TASK_NAMES
    assert "QuoteForge Safety Check" in EXPECTED_TASK_NAMES
    assert "QuoteForge Infrastructure Check" in EXPECTED_TASK_NAMES
    # All names are unique
    assert len(EXPECTED_TASK_NAMES) == len({j.name for j in SCHEDULED_JOBS})
    assert "QuoteForge Daily Maintenance" in EXPECTED_TASK_NAMES


def test_monitor_and_installer_cannot_drift():
    # The health check's EXPECTED_TASKS must be the SAME list the installer uses.
    from quoteforge.automation.healthcheck import EXPECTED_TASKS
    assert EXPECTED_TASKS == EXPECTED_TASK_NAMES


def test_create_command_targets_admin_and_root():
    job = SCHEDULED_JOBS[0]
    cmd = build_create_command(job, python="py.exe")
    assert cmd[:4] == ["schtasks", "/Create", "/TN", job.name]
    assert "/F" in cmd  # force-overwrite so re-install is idempotent
    tr = cmd[cmd.index("/TR") + 1]
    assert "quoteforge.admin" in tr
    assert job.admin_args in tr


def test_delete_command():
    cmd = build_delete_command(SCHEDULED_JOBS[0])
    assert cmd[:2] == ["schtasks", "/Delete"]
    assert cmd[-1] == "/F"


def test_install_dry_run_executes_nothing():
    calls = []
    summary = install_schedule(dry_run=True, runner=lambda *a, **k: calls.append(a))
    assert summary["dry_run"] is True
    assert summary["total"] == len(SCHEDULED_JOBS)
    assert calls == []  # runner never invoked on a dry run


def test_install_invokes_runner_per_job():
    class FakeProc:
        returncode = 0
        stdout = "SUCCESS"
        stderr = ""
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        return FakeProc()

    summary = install_schedule(runner=fake_runner)
    assert len(calls) == len(SCHEDULED_JOBS)
    assert summary["errors"] == 0
    assert all(r["status"] == "ok" for r in summary["results"])


def test_install_only_targets_named_jobs():
    class FakeProc:
        returncode = 0; stdout = "SUCCESS"; stderr = ""
    calls = []
    def fake_runner(cmd, **kwargs):
        calls.append(cmd); return FakeProc()
    summary = install_schedule(only=["QuoteForge Etsy Order Poll"],
                               runner=fake_runner)
    assert summary["total"] == 1
    assert len(calls) == 1
    assert "QuoteForge Etsy Order Poll" in " ".join(calls[0])


def test_install_reports_failures():
    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "Access is denied"
    summary = install_schedule(runner=lambda *a, **k: FakeProc())
    assert summary["errors"] == len(SCHEDULED_JOBS)
    assert "denied" in format_install_text(summary).lower()


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_install_schedule_dry_run(capsys):
    rc = admin.main(["install-schedule", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry run" in out.lower()
    assert "QuoteForge Daily Report" in out
    assert "quoteforge.admin" in out


def test_cli_install_schedule_registered():
    assert "install-schedule" in admin.COMMANDS
