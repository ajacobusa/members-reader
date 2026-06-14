"""POC reporting: render the validation dashboard and the labelled POC site.

build_dashboard() turns run_validation()'s results into an owner-facing HTML
dashboard (section-7 metrics + go/no-go + issue buckets). build_poc_site() takes
the live deployed storefront and stamps it as an unmistakable TEST-ONLY POC site
(banner + title) so it can never be mistaken for production.
"""
from __future__ import annotations

from pathlib import Path

_AGENTS = {"customer": "Customer", "routing": "Routing", "tracking": "Tracking",
           "policy": "Policy", "financial": "Financial", "admin": "Admin QA"}


def _css() -> str:
    """Inline dashboard stylesheet."""
    return (
        "body{font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;margin:0;"
        "background:#f4f6f5;color:#1d2a24}"
        ".poc{background:repeating-linear-gradient(45deg,#7a1d1d,#7a1d1d 16px,"
        "#9a2a2a 16px,#9a2a2a 32px);color:#fff;text-align:center;font-weight:800;"
        "letter-spacing:.08em;padding:9px;font-size:13px}"
        ".wrap{max-width:1000px;margin:0 auto;padding:22px}"
        "h1{font-size:24px;margin:6px 0}"
        ".verdict{padding:16px 20px;border-radius:14px;font-weight:800;font-size:20px;"
        "margin:14px 0;color:#fff}"
        ".go{background:linear-gradient(135deg,#1d6048,#103d2e)}"
        ".nogo{background:linear-gradient(135deg,#9a2a2a,#6f1c1c)}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));"
        "gap:12px;margin:16px 0}"
        ".card{background:#fff;border:1px solid #e3e8e5;border-radius:12px;padding:14px}"
        ".card b{display:block;font-size:26px;color:#103d2e}"
        ".card span{font-size:12px;color:#6b7a72}"
        "table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;"
        "overflow:hidden;margin:10px 0;font-size:14px}"
        "th{background:#103d2e;color:#fff;text-align:left;padding:9px 12px;font-size:12px}"
        "td{padding:8px 12px;border-top:1px solid #eef2f0}"
        ".ok{color:#1d7a47;font-weight:700}.bad{color:#b3261e;font-weight:700}"
        ".sev{display:inline-block;padding:1px 9px;border-radius:999px;font-size:11px;"
        "font-weight:800;color:#fff}"
        ".critical{background:#b3261e}.high{background:#d97706}.medium{background:#0369a1}"
        ".low{background:#6b7280}h2{font-size:16px;margin:22px 0 6px}")


def _verdict_html(results: dict) -> str:
    """The big GO / NO-GO banner with the blocking reason."""
    m = results["metrics"]
    if results["go"]:
        return ('<div class="verdict go">✅ GO — all critical &amp; high checks '
                f'passed ({m["passed"]}/{m["total_checks"]}).</div>')
    blockers = m["critical_fail"] + m["high_fail"]
    return ('<div class="verdict nogo">⛔ NO-GO — '
            f'{blockers} blocking issue(s): {m["critical_fail"]} critical, '
            f'{m["high_fail"]} high. Fix before launch.</div>')


def build_dashboard(results: dict, out_path, generated_at: str = "") -> Path:
    """Write the POC validation dashboard HTML; returns the path."""
    out_path = Path(out_path)
    m = results["metrics"]
    cards = [("Test orders", m["scenarios_total"]),
             ("Scenarios passed", f'{m["scenarios_passed"]}/{m["scenarios_total"]}'),
             ("Checks passed", f'{m["passed"]}/{m["total_checks"]}'),
             ("Coverage", f'{m["coverage_pct"]}%'),
             ("Critical fails", m["critical_fail"]), ("High fails", m["high_fail"])]
    card_html = "".join(f'<div class="card"><b>{v}</b><span>{k}</span></div>'
                        for k, v in cards)

    scen_rows = "".join(
        f'<tr><td>{s["id"]}</td><td>{s["name"]}</td><td>{s["checks"]}</td>'
        f'<td class="{"ok" if s["passed"] else "bad"}">'
        f'{"PASS" if s["passed"] else "FAIL"}</td></tr>'
        for s in results["scenarios"])

    chk_rows = "".join(
        f'<tr><td><span class="sev {c["severity"]}">{c["severity"]}</span></td>'
        f'<td>{_AGENTS.get(c["agent"], c["agent"])}</td><td>{c["name"]}</td>'
        f'<td class="{"ok" if c["ok"] else "bad"}">{"PASS" if c["ok"] else "FAIL"}</td>'
        f'<td>{c["detail"]}</td></tr>'
        for c in sorted(results["checks"], key=lambda x: (x["ok"], x["severity"])))

    issues = [c for sev in ("critical", "high", "medium", "low")
              for c in results["issues"][sev]]
    issue_html = ("".join(
        f'<tr><td><span class="sev {c["severity"]}">{c["severity"]}</span></td>'
        f'<td>{c["name"]}</td><td>{c["detail"]}</td></tr>' for c in issues)
        or '<tr><td colspan="3" class="ok">No issues found.</td></tr>')

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>POC site — Validation Dashboard (TEST ONLY)</title>"
        f"<style>{_css()}</style></head><body>"
        "<div class='poc'>⚠ POC / UAT — TEST ENVIRONMENT — NOT THE LIVE SITE ⚠</div>"
        "<div class='wrap'>"
        "<h1>QuoteForge — POC End-to-End Validation</h1>"
        f"<div style='color:#6b7a72;font-size:13px'>Generated {generated_at} · "
        "drives the real production code against a seeded test database</div>"
        f"{_verdict_html(results)}"
        f"<div class='cards'>{card_html}</div>"
        "<h2>Required test scenarios (15)</h2>"
        "<table><tr><th>#</th><th>Scenario</th><th>Checks</th><th>Result</th></tr>"
        f"{scen_rows}</table>"
        "<h2>Issues by severity (optimization backlog)</h2>"
        "<table><tr><th>Severity</th><th>Issue</th><th>Detail</th></tr>"
        f"{issue_html}</table>"
        "<h2>All validation checks</h2>"
        "<table><tr><th>Severity</th><th>Agent</th><th>Check</th><th>Result</th>"
        f"<th>Detail</th></tr>{chk_rows}</table>"
        "<div class='poc' style='margin-top:20px'>POC site — for testing only — "
        "never the primary site</div>"
        "</div></body></html>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


_POC_BANNER = (
    "<div style=\"position:sticky;top:0;z-index:99999;background:"
    "repeating-linear-gradient(45deg,#7a1d1d,#7a1d1d 16px,#9a2a2a 16px,#9a2a2a 32px);"
    "color:#fff;text-align:center;font:800 13px/1.4 system-ui,sans-serif;"
    "letter-spacing:.08em;padding:8px\">⚠ POC SITE — TEST ENVIRONMENT — "
    "NOT THE LIVE STORE — orders here are not real ⚠</div>")


def build_poc_site(src_html, out_path) -> Path:
    """Snapshot the deployed storefront as an unmistakable TEST-ONLY POC site:
    inject the warning banner and retitle it. Returns the written path."""
    src_html, out_path = Path(src_html), Path(out_path)
    html = src_html.read_text(encoding="utf-8")
    # Retitle so the browser tab clearly reads POC.
    import re
    html = re.sub(r"<title>.*?</title>", "<title>POC site — TEST ONLY</title>",
                  html, count=1, flags=re.DOTALL)
    # Inject the sticky banner right after <body...>.
    if "<body" in html:
        html = re.sub(r"(<body[^>]*>)", r"\1" + _POC_BANNER, html, count=1)
    else:
        html = _POC_BANNER + html
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
