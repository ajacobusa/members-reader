"""The recurring code-outcome auditor that feeds the infra-check agent.

Every finding is grounded (parsed from real source / derived from infra_check's
AST). The daily sweep covers ALL modules in one consistent pass and alerts the
owner if any module has a smell.
"""
import quoteforge.automation.code_auditor as ca


# ───────────────────────────────────────────── full sweep covers every module
def test_list_modules_covers_the_package():
    mods = ca.list_modules()
    assert "automation/code_auditor.py" in mods
    assert all(not m.endswith("__init__.py") for m in mods)
    assert len(mods) > 50                                  # the whole package


# ───────────────────────────────────────────── grounded smells
def test_smells_flags_silent_and_bare_except_and_todo():
    src = (
        "def f():\n"
        "    try:\n"
        "        risky()\n"
        "    except Exception:\n"
        "        pass\n"          # silent_except
        "def g():\n"
        "    try:\n"
        "        risky()\n"
        "    except:\n"           # bare_except
        "        log()\n"
        "x = 1  # TODO: revisit\n"  # todo_marker
    )
    kinds = {s["kind"] for s in ca._smells(src)}
    assert {"silent_except", "bare_except", "todo_marker"} <= kinds


def test_smells_does_not_flag_a_handled_except():
    # An except that logs/alerts/re-raises is NOT a silent-failure smell.
    src = ("def f():\n"
           "    try:\n"
           "        risky()\n"
           "    except Exception as e:\n"
           "        logger.warning(e)\n")
    assert [s for s in ca._smells(src) if s["kind"] == "silent_except"] == []


def test_smells_reports_syntax_error_grounded():
    out = ca._smells("def broken(:\n  pass\n")
    assert out and out[0]["kind"] == "syntax_error"


# ───────────────────────────────────────────── coverage (grounded via AST)
def test_infra_referenced_names_is_grounded():
    # infra_check genuinely references these guards, so they must appear.
    names = ca._infra_referenced_names()
    assert "check_safety_rails" in names and "route_order" in names


def test_audit_module_reports_real_module():
    r = ca.audit_module("automation/code_auditor.py")
    assert r["module"] == "automation/code_auditor.py"
    assert isinstance(r["coverage_gaps"], list)
    assert "format_audit_text" in r["public_defs"]


# ───────────────────────────────────────────── the ratchet (alert on NEW only)
def _one_smell(m, protected=None):
    return {"module": m, "public_defs": [], "coverage_gaps": [],
            "smells": [{"kind": "silent_except", "line": 5, "detail": "swallowed"}],
            "ok": False}


def test_run_full_audit_alerts_on_a_regression(monkeypatch):
    import quoteforge.admin as admin
    monkeypatch.setattr(ca, "list_modules", lambda: ["b.py"])
    monkeypatch.setattr(ca, "_infra_referenced_names", lambda: set())
    monkeypatch.setattr(ca, "audit_module", _one_smell)
    monkeypatch.setattr(ca, "load_baseline", lambda: {})        # nothing accepted yet
    alerts = []
    monkeypatch.setattr(admin, "_alert", lambda s, b, what=None: alerts.append(s))
    r = ca.run_full_audit(send=True)
    assert r["alerted"] is True and r["regressions"][0]["module"] == "b.py"


def test_run_full_audit_quiet_when_smell_is_in_baseline(monkeypatch):
    import quoteforge.admin as admin
    monkeypatch.setattr(ca, "list_modules", lambda: ["b.py"])
    monkeypatch.setattr(ca, "_infra_referenced_names", lambda: set())
    monkeypatch.setattr(ca, "audit_module", _one_smell)
    # The smell is already accepted in the baseline -> NOT a regression -> no alert.
    monkeypatch.setattr(ca, "load_baseline", lambda: {"b.py": {"silent_except": 1}})
    alerts = []
    monkeypatch.setattr(admin, "_alert", lambda s, b, what=None: alerts.append(s))
    r = ca.run_full_audit(send=True)
    assert r["alerted"] is False and not alerts and r["ok"] is True
    assert r["flagged"] == ["b.py"]                  # still tracked, just not alerted


def test_regressions_only_counts_above_baseline():
    results = [{"module": "m.py",
                "smells": [{"kind": "silent_except", "line": 1, "detail": "x"},
                           {"kind": "silent_except", "line": 2, "detail": "y"}]}]
    assert ca.regressions(results, {"m.py": {"silent_except": 2}}) == []   # at baseline
    regs = ca.regressions(results, {"m.py": {"silent_except": 1}})         # one new
    assert regs and regs[0]["count"] == 2 and regs[0]["accepted"] == 1


def test_live_codebase_has_no_smell_beyond_committed_baseline():
    # The committed audit_baseline.json must keep the live sweep green (ratchet held).
    r = ca.run_full_audit(send=False)
    assert r["modules"] > 50 and r["regressions"] == [] and r["ok"] is True


def test_audit_sweep_is_automated_in_render_cron():
    # REGRESSION: the daily audit sweep must be wired into a Render cron so it
    # actually RUNS in production, not just defined in the Windows scheduler.
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent
            / "render.yaml").read_text(encoding="utf-8")
    assert "quoteforge.admin audit" in text          # the daily-guards cron runs it


# ───────────────────────────────────────────── wiring (keeps infra-check green)
def test_audit_command_and_job_are_wired():
    import quoteforge.admin as admin
    from quoteforge.automation.scheduler import SCHEDULED_JOBS, EXPECTED_TASK_NAMES
    assert "audit" in admin.COMMANDS
    job = next((j for j in SCHEDULED_JOBS if j.admin_args == "audit"), None)
    assert job is not None and job.name == "QuoteForge Code Audit Sweep"
    # The healthcheck monitors exactly the scheduled jobs (no drift introduced).
    assert job.name in EXPECTED_TASK_NAMES
