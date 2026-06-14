"""POC runner: orchestrate validation + dashboard + site snapshot into POC/.

`run_poc(poc_dir)` runs the full validation against an isolated test DB under
POC/poc_data/, writes the dashboard and the labelled POC site, and returns the
results (including the go/no-go verdict). For TESTING ONLY - never production.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

# Repo root = three levels up (quoteforge/poc/runner.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
POC_DIR = _REPO_ROOT / "POC"
DOCS_INDEX = _REPO_ROOT / "docs" / "index.html"


def run_poc(poc_dir=None, docs_index=None) -> dict:
    """Run the POC end-to-end validation and write its artifacts. Returns the
    results dict (with 'go', metrics, scenarios, issues)."""
    from quoteforge.poc.harness import run_validation
    from quoteforge.poc.report import build_dashboard, build_poc_site
    poc_dir = Path(poc_dir or POC_DIR)
    docs_index = Path(docs_index or DOCS_INDEX)
    data_dir = poc_dir / "poc_data"

    results = run_validation(data_dir / "poc.db", data_dir)
    stamp = datetime.now().isoformat(timespec="seconds")
    dash = build_dashboard(results, poc_dir / "poc_dashboard.html", stamp)
    site = None
    if docs_index.exists():
        site = build_poc_site(docs_index, poc_dir / "poc_site" / "index.html")
    return {"results": results, "dashboard": dash, "site": site, "generated_at": stamp}


def format_summary(results: dict) -> str:
    """One-screen console summary of a POC run."""
    m = results["metrics"]
    lines = ["=" * 62, "POC END-TO-END VALIDATION - TEST ONLY", "=" * 62,
             f"  Verdict        : {'GO' if results['go'] else 'NO-GO'}",
             f"  Checks passed  : {m['passed']}/{m['total_checks']} ({m['coverage_pct']}%)",
             f"  Scenarios      : {m['scenarios_passed']}/{m['scenarios_total']} passed",
             f"  Blocking fails : {m['critical_fail']} critical, {m['high_fail']} high",
             f"  Other fails    : {m['medium_fail']} medium, {m['low_fail']} low"]
    fails = [c for c in results["checks"] if not c["ok"]]
    if fails:
        lines.append("  Failures:")
        for c in sorted(fails, key=lambda x: x["severity"]):
            lines.append(f"    [{c['severity']:<8}] {c['name']} - {c['detail']}")
    lines.append("=" * 62)
    return "\n".join(lines)
