"""Tests for the daily self-healing site doctor (storefront QA bot).

The doctor reads the REAL built page (docs/index.html) for its checks, so these
tests double as a live verification that the shipped page passes the audit. The
heal/regression runners are injected so nothing rebuilds or spawns pytest here.
"""
from quoteforge.automation import site_doctor as sd


def _fake_test_runner(*a, **k):
    """Stands in for subprocess.run: a passing pytest invocation."""
    class P:
        returncode = 0
        stdout = "42 passed in 1.00s"
        stderr = ""
    return P()


def test_built_page_passes_all_checks():
    """The committed docs/index.html satisfies every audit guarantee."""
    html = sd._read_page()
    assert html, "docs/index.html missing - run rebuild-site"
    for c in sd._page_checks(html):
        assert c["status"] == "OK", f"{c['name']}: {c['detail']}"


def test_docs_ratchet_holds():
    """Storefront-critical modules stay 100% docstring'd (incl. the doctor)."""
    c = sd.check_docs_ratchet()
    assert c["status"] == "OK", c["detail"]


def test_doctor_overall_ok_with_fake_regression(monkeypatch):
    """End-to-end run (no heal needed, fake pytest) reports overall OK.
    The untracked-code tripwire is pinned OK so a developer's WIP files don't
    fail an unrelated test run (the real check still runs nightly)."""
    monkeypatch.setattr(sd, "check_untracked_code",
                        lambda runner=None: {"name": "untracked_code",
                                             "status": "OK", "detail": "pinned"})
    r = sd.run_site_doctor(heal=False, regression=True,
                           test_runner=_fake_test_runner)
    assert r["overall"] == "OK", sd.format_site_doctor_text(r)
    names = {c["name"] for c in r["checks"]}
    assert {"page_fresh", "fonts_lazy", "jsonld", "alt_coverage",
            "assets_integrity", "orphan_assets", "occasion_filter",
            "design_count", "editor_hooks", "docs_ratchet",
            "untracked_code", "regression"} <= names


def test_doctor_heals_by_rebuilding(monkeypatch, tmp_path):
    """A page-level failure triggers exactly one rebuild, then re-checks."""
    calls = []
    # Break one page check: pretend the JSON-LD block disappeared.
    monkeypatch.setattr(sd, "check_jsonld",
                        lambda html: {"name": "jsonld", "status": "FAIL",
                                      "detail": "forced"})
    r = sd.run_site_doctor(heal=True, regression=False,
                           rebuild_runner=lambda: calls.append("rebuild") or "rebuilt (fake)")
    assert calls == ["rebuild"]                  # healed once, not in a loop
    assert any("rebuilt" in h for h in r["healed"])


def test_regression_failure_is_reported_not_healed():
    """A failing regression run flips overall to FAIL (never auto-'fixed')."""
    def failing_runner(*a, **k):
        class P:
            returncode = 1
            stdout = "1 failed, 41 passed"
            stderr = ""
        return P()
    r = sd.run_site_doctor(heal=False, regression=True,
                           test_runner=failing_runner)
    assert r["overall"].startswith("FAIL")
    reg = next(c for c in r["checks"] if c["name"] == "regression")
    assert reg["status"] == "FAIL" and "1 failed" in reg["detail"]


def test_untracked_code_tripwire():
    """New code files git doesn't know about are flagged (report-only);
    junk extensions (logs/caches) are ignored."""
    def fake_git(args, **k):
        class P:
            returncode = 0
            stdout = ("?? newfeature/widget.py\n"
                      "?? notes/idea.md\n"
                      "?? stock_dashboard/cache/x.log\n"   # junk ext - ignored
                      " M tracked_and_modified.py\n")      # tracked - not ours
            stderr = ""
        return P()
    c = sd.check_untracked_code(runner=fake_git)
    assert c["status"] == "FAIL"
    assert "2 unbacked code file(s)" in c["detail"]
    assert "git add" in c["detail"]                # tells you the exact fix


def test_untracked_code_clean_tree_ok():
    """A clean tree (or only junk untracked) passes."""
    def fake_git(args, **k):
        class P:
            returncode = 0
            stdout = "?? logs/run.log\n"
            stderr = ""
        return P()
    c = sd.check_untracked_code(runner=fake_git)
    assert c["status"] == "OK"


def test_site_doctor_is_scheduled_daily():
    """The bot is wired into the one-source-of-truth schedule (so healthcheck
    monitors it too) and runs daily after the rebuild + backup."""
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    job = next(j for j in SCHEDULED_JOBS if j.name == "QuoteForge Site Doctor")
    assert job.admin_args == "site-doctor email"
    assert "/SC" in job.schtasks_flags and "DAILY" in job.schtasks_flags
