import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from stock_dashboard import resume

UTC = dt.timezone.utc


def _fake_run(record, returncode=0):
    def run(cmd, **kw):
        record.append(cmd)
        return SimpleNamespace(returncode=returncode, stdout="", stderr="")
    return run


def test_build_create_cmd_shape():
    at = dt.datetime(2026, 6, 11, 0, 0, tzinfo=UTC)
    cmd = resume.build_create_cmd(at, Path("C:/app"), python="C:/py/python.exe")
    assert cmd[0] == "schtasks" and "/create" in cmd
    assert cmd[cmd.index("/tn") + 1] == resume.TASK_NAME
    assert cmd[cmd.index("/sc") + 1] == "ONCE"
    # the action references both the interpreter and run_daily.py
    tr = cmd[cmd.index("/tr") + 1]
    assert "python.exe" in tr and "run_daily.py" in tr
    # one-shot start time/date present
    assert "/st" in cmd and "/sd" in cmd


def test_schedule_resume_success():
    calls = []
    ok = resume.schedule_resume(dt.datetime(2026, 6, 11, 9, 30, tzinfo=UTC),
                                Path("C:/app"), python="py", run=_fake_run(calls))
    assert ok is True
    assert calls and calls[0][0] == "schtasks"


def test_schedule_resume_soft_fails_on_nonzero():
    ok = resume.schedule_resume(dt.datetime(2026, 6, 11, 9, 30, tzinfo=UTC),
                                Path("C:/app"), run=_fake_run([], returncode=1))
    assert ok is False


def test_schedule_resume_soft_fails_on_exception():
    def boom(cmd, **kw):
        raise OSError("schtasks missing")
    ok = resume.schedule_resume(dt.datetime(2026, 6, 11, 9, 30, tzinfo=UTC),
                                Path("C:/app"), run=boom)
    assert ok is False


def test_cancel_resume_delete_command():
    calls = []
    resume.cancel_resume(run=_fake_run(calls))
    assert calls[0][:2] == ["schtasks", "/delete"]
    assert resume.TASK_NAME in calls[0]


def test_cancel_resume_not_found_is_soft():
    assert resume.cancel_resume(run=_fake_run([], returncode=1)) is False
