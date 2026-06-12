"""Daily self-healing SITE doctor — the storefront's automated QA bot.

The infra agent (`maintenance.py`) heals databases/backups/jobs. THIS agent owns
the customer-facing website (`docs/index.html`): every day it re-verifies the
optimizations from WEBSITE_AUDIT.md still hold, and when a page-level problem is
found it heals itself by REBUILDING the site from source and re-checking.

Daily checks (each maps to an audit guarantee):
  1. page_fresh        - docs/index.html exists and was rebuilt recently
  2. fonts_lazy        - editor-only fonts load async (media=print onload swap);
                         core fonts remain render-blocking; noscript fallback kept
  3. jsonld            - SEO structured data parses and still has
                         Organization / WebSite / Product(AggregateOffer)
  4. alt_coverage      - every <img> on the page carries alt text
  5. assets_integrity  - every assets/... file the page references exists on disk
                         (a missing file = broken image for a customer)
  6. orphan_assets     - assets on disk that nothing references (repo bloat)
  7. occasion_filter   - apostrophe occasions stay JS-escaped and product cards
                         keep their exact data-occ key (the two past filter bugs)
  8. design_count      - the grid still carries one design per occasion (>= 13)
  9. editor_hooks      - the personalization editor's critical JS is present
                         (drag toggle, rotation, photo zoom) - a rendering
                         regression tripwire
 10. docs_ratchet      - the storefront-critical modules stay 100% docstring'd

Self-healing (only safe, reversible actions):
  - any page-level failure  -> rebuild docs/index.html from source, re-check
  - orphaned assets         -> prune them (they are regenerated on rebuild)
  - regression test failure -> NEVER auto-"fixed"; reported loudly for a human

Run:  python -m quoteforge.admin site-doctor            # check + heal + print
      python -m quoteforge.admin site-doctor email      # also email on problems
      python -m quoteforge.admin site-doctor --no-heal   # report only
Scheduled daily at 02:30 (after the 01:50 rebuild and the 02:00 backup).
"""
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

# Repo root (…/quoteforge/automation/site_doctor.py -> two levels up).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The built storefront page + its on-disk assets (what GitHub Pages serves).
DOCS = PROJECT_ROOT / "docs"
PAGE = DOCS / "index.html"
ASSETS = DOCS / "assets"
# "Fresh" = rebuilt within this window (nightly rebuild runs at 01:50).
MAX_PAGE_AGE_HOURS = 26
# The grid must keep at least one design per calendar occasion + extras.
MIN_DESIGNS = 13
# What the docs ratchet scans. The WHOLE package is in: every function, class,
# and module header must carry a docstring, and coverage can never regress.
CRITICAL_MODULES = [
    "quoteforge",                      # directories are scanned recursively
]
# Fast regression subset covering the storefront's behavior (UI hooks, SEO,
# a11y, occasion logic, personalization editor). The FULL suite still runs in
# CI on every push.
REGRESSION_TESTS = [
    "quoteforge_tests/test_seo_a11y.py",
    "quoteforge_tests/test_basket_photo.py",
    "quoteforge_tests/test_generalized_titles.py",
    "quoteforge_tests/test_occasion_quotes.py",
    "quoteforge_tests/test_packages_exit.py",
]


def _read_page() -> str:
    """The built page's HTML, or '' when it does not exist yet."""
    try:
        return PAGE.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


# ── The checks (each returns {name, status: OK|FAIL, detail}) ────────────

def check_page_fresh() -> dict:
    """Page exists and was rebuilt within MAX_PAGE_AGE_HOURS."""
    if not PAGE.exists():
        return {"name": "page_fresh", "status": "FAIL", "detail": "docs/index.html missing"}
    age_h = (datetime.now().timestamp() - PAGE.stat().st_mtime) / 3600
    ok = age_h <= MAX_PAGE_AGE_HOURS
    return {"name": "page_fresh", "status": "OK" if ok else "FAIL",
            "detail": f"age {age_h:.1f}h (max {MAX_PAGE_AGE_HOURS}h)"}


def check_fonts_lazy(html: str) -> dict:
    """Editor fonts stay async-loaded; core fonts stay blocking; noscript kept."""
    links = re.findall(r'<link\b[^>]*fonts\.googleapis\.com[^>]*>', html)
    core_ok = any("Cormorant" in l and 'media="print"' not in l for l in links)
    async_ok = any("Dancing+Script" in l and 'media="print"' in l
                   and "this.media='all'" in l for l in links)
    noscript_ok = "<noscript><link" in html
    ok = core_ok and async_ok and noscript_ok
    return {"name": "fonts_lazy", "status": "OK" if ok else "FAIL",
            "detail": f"core={core_ok} async={async_ok} noscript={noscript_ok}"}


def check_jsonld(html: str) -> dict:
    """SEO structured data still parses and keeps its three node types."""
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if not m:
        return {"name": "jsonld", "status": "FAIL", "detail": "JSON-LD block missing"}
    try:
        types = {n.get("@type") for n in json.loads(m.group(1))["@graph"]}
    except Exception as exc:  # noqa: BLE001
        return {"name": "jsonld", "status": "FAIL", "detail": f"invalid JSON: {exc}"}
    ok = {"Organization", "WebSite", "Product"} <= types
    return {"name": "jsonld", "status": "OK" if ok else "FAIL",
            "detail": f"types={sorted(t for t in types if t)}"}


def check_alt_coverage(html: str) -> dict:
    """Accessibility: every <img> tag carries alt text."""
    imgs = re.findall(r'<img\b[^>]*>', html)
    missing = [t for t in imgs if "alt=" not in t]
    return {"name": "alt_coverage",
            "status": "OK" if not missing else "FAIL",
            "detail": f"{len(imgs)} imgs, {len(missing)} missing alt"}


def check_assets_integrity(html: str) -> dict:
    """Every assets/<file> the page references must exist (else broken images)."""
    refs = set(re.findall(r'assets/([A-Za-z0-9_\-.]+)', html))
    present = set(os.listdir(ASSETS)) if ASSETS.exists() else set()
    missing = sorted(refs - present)
    return {"name": "assets_integrity",
            "status": "OK" if not missing else "FAIL",
            "detail": (f"{len(refs)} referenced, all present" if not missing
                       else f"missing: {missing[:5]}")}


def check_assets_render(html: str, assets_dir: Path = None) -> dict:
    """Rendering tripwire: every referenced raster image must actually DECODE.

    assets_integrity only proves the file exists; a truncated or corrupt file
    still ships a broken image to the customer. This opens each referenced
    asset with Pillow (verify = header + structure check, no full decode of
    huge files) so a bad render surfaces nightly and is healed by rebuild.
    ``assets_dir`` is injectable for unit tests."""
    from PIL import Image
    assets_dir = assets_dir if assets_dir is not None else ASSETS
    refs = sorted(set(re.findall(r'assets/([A-Za-z0-9_\-.]+)', html)))
    raster = [f for f in refs if f.lower().endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".gif"))]
    corrupt = []
    for f in raster:
        p = assets_dir / f
        if not p.exists():
            continue            # missing files are assets_integrity's finding
        try:
            with Image.open(p) as im:
                im.verify()
        except Exception:  # noqa: BLE001
            corrupt.append(f)
    return {"name": "assets_render",
            "status": "OK" if not corrupt else "FAIL",
            "detail": (f"{len(raster)} images decode cleanly" if not corrupt
                       else f"corrupt: {corrupt[:5]}")}


def check_orphan_assets(html: str) -> dict:
    """Assets on disk that nothing references - repo bloat we prune on heal."""
    refs = set(re.findall(r'assets/([A-Za-z0-9_\-.]+)', html))
    present = set(os.listdir(ASSETS)) if ASSETS.exists() else set()
    orphans = sorted(f for f in present - refs
                     if f.endswith((".jpg", ".jpeg", ".png", ".webp")))
    return {"name": "orphan_assets",
            "status": "OK" if not orphans else "FAIL",
            "detail": f"{len(orphans)} orphaned file(s)", "orphans": orphans}


def check_occasion_filter(html: str) -> dict:
    """The two historical filter bugs stay fixed: apostrophes JS-escaped in the
    occasion tiles, and product cards carry an exact data-occ key."""
    escaped = "shopByOccasion('Mother\\'s Day'" in html
    unescaped = "shopByOccasion('Mother's Day'" in html      # the original bug
    dataocc = "data-occ=" in html
    ok = escaped and not unescaped and dataocc
    return {"name": "occasion_filter", "status": "OK" if ok else "FAIL",
            "detail": f"escaped={escaped} unescaped_bug={unescaped} data-occ={dataocc}"}


def check_design_count(html: str) -> dict:
    """The grid keeps one design per occasion (no dupes, none dropped)."""
    m = re.search(r'const DATA = (\[.*?\]);', html, re.S)
    if not m:
        return {"name": "design_count", "status": "FAIL", "detail": "DATA array missing"}
    try:
        data = json.loads(m.group(1))
    except Exception as exc:  # noqa: BLE001
        return {"name": "design_count", "status": "FAIL", "detail": f"DATA invalid: {exc}"}
    occs = [d.get("occ") for d in data]
    ok = len(data) >= MIN_DESIGNS and len(occs) == len(set(occs))
    return {"name": "design_count", "status": "OK" if ok else "FAIL",
            "detail": f"{len(data)} designs, unique occasions={len(occs) == len(set(occs))}"}


def check_editor_hooks(html: str) -> dict:
    """Rendering tripwire: the personalization editor's critical JS functions
    must all be present, or buyers can't customize (drag/rotate/zoom/basket)."""
    hooks = ["function setDragMode", "function setRot", "function setPhotoZoom",
             "function addToBasket", "function shopByOccasion", "function render"]
    missing = [h for h in hooks if h not in html]
    return {"name": "editor_hooks",
            "status": "OK" if not missing else "FAIL",
            "detail": "all present" if not missing else f"missing: {missing}"}


# File extensions that count as "code" worth backing up. Anything else
# (caches, logs, images dumped by tools) is left to a human to triage.
CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".md", ".html",
             ".css", ".json", ".yml", ".yaml", ".toml", ".sh", ".ps1", ".bat")


def check_untracked_code(runner=subprocess.run) -> dict:
    """Backup tripwire: flag CODE files git doesn't know about.

    The nightly backup auto-commits only TRACKED files (deliberately - so junk
    and secrets can never sneak into GitHub). The cost of that safety is that a
    brand-new file isn't backed up until someone `git add`s it. This check makes
    that visible the SAME DAY in the doctor's email instead of weeks later.
    Report-only: the doctor never commits unknown files itself.
    """
    try:
        p = runner(["git", "status", "--porcelain", "--untracked-files=all"],
                   cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                   timeout=60)
        untracked = [l[3:].strip() for l in (p.stdout or "").splitlines()
                     if l.startswith("??")]
        code = [f for f in untracked if f.lower().endswith(CODE_EXTS)]
        return {"name": "untracked_code",
                "status": "OK" if not code else "FAIL",
                "detail": ("all code files tracked & backed up" if not code
                           else f"{len(code)} unbacked code file(s) - "
                                f"run: git add {' '.join(code[:3])}"
                                + (" ..." if len(code) > 3 else ""))}
    except Exception as exc:  # noqa: BLE001
        return {"name": "untracked_code", "status": "FAIL", "detail": f"{exc}"}


def check_github_sync(runner=subprocess.run) -> dict:
    """High-availability tripwire: local HEAD must be ON GitHub.

    The nightly backup pushes to GitHub, but a push can fail silently for weeks
    (expired token, network) - leaving every backup copy on ONE machine. This
    asks GitHub directly (ls-remote, no fetch) whether the current branch's HEAD
    commit exists remotely, so a broken push pipeline surfaces the next morning.
    """
    try:
        head = runner(["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT),
                      capture_output=True, text=True, timeout=30).stdout.strip()
        branch = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                        timeout=30).stdout.strip()
        remote = runner(["git", "ls-remote", "origin", branch],
                        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                        timeout=60).stdout.strip().split("\t")[0]
        ok = bool(head) and head == remote
        return {"name": "github_sync", "status": "OK" if ok else "FAIL",
                # ASCII only: the scheduled-task console is cp1252 and a unicode
                # checkmark here crashed the whole report once. Plain text wins.
                "detail": (f"{branch} HEAD is on GitHub" if ok else
                           f"{branch}: local {head[:7]} vs GitHub "
                           f"{(remote or 'unreachable')[:7]} - push is broken/behind")}
    except Exception as exc:  # noqa: BLE001
        return {"name": "github_sync", "status": "FAIL", "detail": f"{exc}"}


def check_docs_ratchet(modules: list = None, root: Path = None) -> dict:
    """Documentation ratchet: every function, class, AND module header in the
    scanned packages must carry a docstring - coverage can only stay at 100%
    or the check fails. ``modules``/``root`` are injectable for unit tests."""
    import ast
    modules = modules if modules is not None else CRITICAL_MODULES
    root = root if root is not None else PROJECT_ROOT
    undocumented = []
    for rel in modules:
        p = root / rel
        if not p.exists():
            continue
        # An entry may be a single file or a package directory (scanned fully).
        files = [p] if p.is_file() else sorted(p.rglob("*.py"))
        for f in files:
            if "__pycache__" in f.parts:
                continue
            tree = ast.parse(f.read_text(encoding="utf-8"))
            relname = f.relative_to(root).as_posix()
            # Module header (skipped for __init__.py, which is often empty).
            if f.name != "__init__.py" and not ast.get_docstring(tree):
                undocumented.append(f"{relname}:1:missing module docstring")
            for n in ast.walk(tree):
                fn = isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                cls = isinstance(n, ast.ClassDef)
                if ((fn or cls) and not n.name.startswith("__")
                        and not ast.get_docstring(n)):
                    undocumented.append(f"{relname}:{n.lineno}:{n.name}")
    return {"name": "docs_ratchet",
            "status": "OK" if not undocumented else "FAIL",
            "detail": ("package 100% documented" if not undocumented
                       else f"{len(undocumented)} undocumented: {undocumented[:5]}")}


# ── Healing actions (safe + reversible only) ─────────────────────────────

def heal_rebuild(runner=None) -> str:
    """Rebuild docs/index.html from source - the universal page-level fix.
    ``runner`` is injectable so tests can fake the rebuild."""
    if runner is not None:
        return runner()
    try:
        from quoteforge.etsy.listing_preview import build_shop_home
        out = build_shop_home(out_path=PAGE, external_assets=True)
        return f"rebuilt {out.name} ({out.stat().st_size // 1024} KB)"
    except Exception as exc:  # noqa: BLE001
        return f"rebuild failed: {exc}"


def heal_prune_orphans(orphans: list) -> str:
    """Delete orphaned asset files (regenerated on rebuild when needed)."""
    removed = 0
    for f in orphans:
        try:
            (ASSETS / f).unlink()
            removed += 1
        except Exception:  # noqa: BLE001
            pass
    return f"pruned {removed}/{len(orphans)} orphaned asset(s)"


# ── Regression tests (report-only; never auto-"fixed") ───────────────────

def run_regression(runner=subprocess.run) -> dict:
    """Run the storefront regression subset (full suite runs in CI on push).
    ``runner`` is injectable so unit tests don't spawn a real pytest. The
    subprocess-level timeout (not a pytest flag) bounds a hung run."""
    import sys
    try:
        p = runner([sys.executable, "-m", "pytest", *REGRESSION_TESTS, "-q"],
                   cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                   timeout=900)
        tail = (p.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
        return {"name": "regression", "status": "OK" if p.returncode == 0 else "FAIL",
                "detail": tail[0][:160]}
    except Exception as exc:  # noqa: BLE001
        return {"name": "regression", "status": "FAIL", "detail": f"{exc}"}


# ── Orchestrator ─────────────────────────────────────────────────────────

def _page_checks(html: str) -> list[dict]:
    """All checks that read the built page (re-run after a heal)."""
    return [check_fonts_lazy(html), check_jsonld(html), check_alt_coverage(html),
            check_assets_integrity(html), check_assets_render(html),
            check_orphan_assets(html), check_occasion_filter(html),
            check_design_count(html), check_editor_hooks(html)]


def run_site_doctor(heal: bool = True, regression: bool = True,
                    rebuild_runner=None, test_runner=subprocess.run) -> dict:
    """Check -> heal -> re-check -> regression. Returns the full report dict.

    With ``heal=False`` it only reports (no rebuild / no prune). The two runner
    params are injectable so the unit tests never rebuild the real site or spawn
    a real pytest run.
    """
    report = {"timestamp": datetime.now().isoformat(timespec="seconds"),
              "healed": [], "checks": []}
    html = _read_page()
    # Report-only checks (never healed): docs ratchet, unbacked-code tripwire,
    # and the GitHub-sync HA tripwire (a silently broken push pipeline).
    extra = [check_docs_ratchet(), check_untracked_code(), check_github_sync()]
    checks = [check_page_fresh(), *_page_checks(html), *extra]

    if heal:
        # Prune orphans first (cheap), then rebuild once for any page failure.
        orphan = next((c for c in checks if c["name"] == "orphan_assets"
                       and c["status"] == "FAIL"), None)
        if orphan:
            report["healed"].append(heal_prune_orphans(orphan.get("orphans", [])))
        page_failed = any(c["status"] == "FAIL" for c in checks
                          if c["name"] not in ("docs_ratchet", "orphan_assets",
                                               "untracked_code", "github_sync"))
        if page_failed:
            report["healed"].append(heal_rebuild(rebuild_runner))
        if report["healed"]:
            # Re-verify everything the heals could have changed.
            html = _read_page()
            checks = [check_page_fresh(), *_page_checks(html), *extra]

    report["checks"] = checks
    if regression:
        report["checks"].append(run_regression(test_runner))

    fails = [c for c in report["checks"] if c["status"] == "FAIL"]
    report["overall"] = "OK" if not fails else f"FAIL ({len(fails)} issue(s))"
    return report


def format_site_doctor_text(r: dict) -> str:
    """Human-readable site-doctor report (printed by the CLI / emailed)."""
    lines = ["=" * 60, f"SITE DOCTOR - {r['overall']} - {r['timestamp']}", "=" * 60]
    for h in r["healed"]:
        lines.append(f"  [HEALED] {h}")
    for c in r["checks"]:
        icon = "[OK]  " if c["status"] == "OK" else "[FAIL]"
        lines.append(f"  {icon} {c['name']:18} {c['detail']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def send_site_doctor_alert(report: dict) -> dict:
    """Email the report when something failed (quiet when everything is OK)."""
    if report["overall"] == "OK":
        return {"status": "ok_no_alert"}
    try:
        from quoteforge.automation.emailer import _send_email
        body = ("<html><body style='font-family:monospace;white-space:pre'>"
                + format_site_doctor_text(report) + "</body></html>")
        return _send_email(f"🩺 Site Doctor: {report['overall']}", body)
    except Exception as exc:  # noqa: BLE001
        return {"status": f"email failed: {exc}"}
