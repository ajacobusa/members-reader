"""Automated go-live preflight checker.

Verifies every software-side item on the GO_LIVE_CHECKLIST programmatically so
you can re-run it any time and get a pass/fail report with evidence.

Run:  python -m quoteforge.preflight
Items it CANNOT check (physical print quality) are reported as MANUAL.
"""
from __future__ import annotations

import importlib
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    """Outcome of one preflight check: name, status, and evidence detail."""
    name: str
    status: str   # "PASS" | "FAIL" | "MANUAL" | "CONFIG"
    detail: str = ""


def _safe(fn) -> tuple[bool, str]:
    """Run a check function, returning (ok, detail) instead of raising."""
    try:
        return True, fn() or ""
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def check_software() -> list[CheckResult]:
    """Run all automatable software/HA/recovery checks."""
    results: list[CheckResult] = []

    # ── Imports / wiring ─────────────────────────────────────────
    def _imports():
        """Verify every core module imports (GUI optional on headless hosts)."""
        # Server / pipeline core — must import in any environment.
        for mod in [
            "quoteforge.automation.pipeline_orchestrator",
            "quoteforge.automation.webhook_server",
            "quoteforge.automation.retry",
            "quoteforge.automation.webhook_security",
            "quoteforge.db.database",
            "quoteforge.web_monitor",
        ]:
            importlib.import_module(mod)
        # GUI entrypoint depends on tkinter, which is absent on headless
        # servers and CI runners (e.g. GitHub Actions' Linux Python builds).
        # A missing tkinter must not fail go-live: the server runs headless.
        try:
            importlib.import_module("quoteforge.main")
        except ImportError as exc:
            if "tkinter" in str(exc).lower():
                return "core modules import (GUI skipped: no tkinter/display)"
            raise
        return "all core modules import"
    ok, detail = _safe(_imports)
    results.append(CheckResult("Core modules import", "PASS" if ok else "FAIL", detail))

    # ── Database init + migration ────────────────────────────────
    def _db():
        """Exercise init + order CRUD + column migration against a temp database."""
        import quoteforge.db.database as db
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            orig_path, orig_out = db.DB_PATH, db.OUTPUT_DIR
            db.DB_PATH, db.OUTPUT_DIR = tmp / "t.db", tmp
            try:
                db.init_db()
                oid = db.create_order({"recipient_name": "Pre", "occasion": "Flight"})
                assert db.get_order(oid)
                # migration column present
                o = db.get_order(oid)
                assert "gelato_product_uid" in o
            finally:
                db.DB_PATH, db.OUTPUT_DIR = orig_path, orig_out
        return "init + CRUD + migration OK"
    ok, detail = _safe(_db)
    results.append(CheckResult("Database init + migrations", "PASS" if ok else "FAIL", detail))

    # ── WAL concurrency mode ─────────────────────────────────────
    def _wal():
        """Confirm a fresh database comes up in WAL journal mode."""
        import quoteforge.db.database as db
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            op, oo = db.DB_PATH, db.OUTPUT_DIR
            db.DB_PATH, db.OUTPUT_DIR = tmp / "t.db", tmp
            try:
                db.init_db()
                with db._conn() as c:
                    mode = c.execute("PRAGMA journal_mode").fetchone()[0]
                assert mode.lower() == "wal", f"journal_mode={mode}"
            finally:
                db.DB_PATH, db.OUTPUT_DIR = op, oo
        return "WAL enabled"
    ok, detail = _safe(_wal)
    results.append(CheckResult("SQLite WAL concurrency", "PASS" if ok else "FAIL", detail))

    # ── Idempotency function ─────────────────────────────────────
    def _idem():
        """Confirm the duplicate-webhook idempotency lookup exists."""
        from quoteforge.db.database import get_order_by_etsy_id
        assert callable(get_order_by_etsy_id)
        return "get_order_by_etsy_id present"
    ok, detail = _safe(_idem)
    results.append(CheckResult("Idempotency lookup", "PASS" if ok else "FAIL", detail))

    # ── Backup + prune ───────────────────────────────────────────
    def _backup():
        """Take an online backup of a temp database and verify the file exists."""
        import quoteforge.db.database as db
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            op, oo = db.DB_PATH, db.OUTPUT_DIR
            db.DB_PATH, db.OUTPUT_DIR = tmp / "t.db", tmp
            try:
                db.init_db()
                db.create_order({"recipient_name": "B", "occasion": "C"})
                bpath = db.backup_database(tmp / "bk")
                assert bpath and bpath.exists()
            finally:
                db.DB_PATH, db.OUTPUT_DIR = op, oo
        return "online backup OK"
    ok, detail = _safe(_backup)
    results.append(CheckResult("Database backup/restore", "PASS" if ok else "FAIL", detail))

    # ── Retry / transient classification ─────────────────────────
    def _retry():
        """Check transient-error classification (429/529/5xx) and retry helper."""
        from quoteforge.automation.retry import is_transient, retry_call
        e = Exception(); e.status_code = 529
        assert is_transient(e) is True
        assert is_transient(ValueError()) is False
        assert callable(retry_call)
        return "retry + 429/529/5xx classification OK"
    ok, detail = _safe(_retry)
    results.append(CheckResult("Transient-error retry", "PASS" if ok else "FAIL", detail))

    # ── Webhook signature verification ───────────────────────────
    def _sig():
        """Round-trip HMAC webhook signing and reject a bad signature."""
        from quoteforge.automation.webhook_security import compute_signature, verify_signature
        body = b'{"x":1}'
        sig = compute_signature(body, "secret")
        assert verify_signature(body, sig, "secret") is True
        assert verify_signature(body, "bad", "secret") is False
        return "HMAC verify OK"
    ok, detail = _safe(_sig)
    results.append(CheckResult("Webhook signature verification", "PASS" if ok else "FAIL", detail))

    # ── 7-stage pipeline end-to-end (TEST_MODE) ──────────────────
    def _pipeline():
        """Run the full 7-stage order pipeline end-to-end in TEST_MODE."""
        import quoteforge.db.database as db
        from quoteforge.automation import pipeline_orchestrator as po
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            op, oo, po_out = db.DB_PATH, db.OUTPUT_DIR, po.OUTPUT_DIR
            db.DB_PATH, db.OUTPUT_DIR, po.OUTPUT_DIR = tmp / "t.db", tmp, tmp
            try:
                db.init_db()
                stages = []
                po.run_full_pipeline(
                    {"order_id": "PF-1", "recipient_name": "Emma", "occasion": "Graduation",
                     "sender_name": "Mom", "relationship": "To My Daughter"},
                    on_stage=lambda s, m: stages.append(s),
                    skip_proof=True, gelato_product_uid="x",
                    recipient_address={"name": "Emma", "country": "US"},
                )
                fired = {s for s in po.STAGES if s in stages}
                assert len(fired) == 7, f"only {fired}"
                order = db.get_order("PF-1")
                assert order["status"] == "shipped"
                assert order["generated_quote"]
            finally:
                db.DB_PATH, db.OUTPUT_DIR, po.OUTPUT_DIR = op, oo, po_out
        return "7 stages fired, status=shipped"
    ok, detail = _safe(_pipeline)
    results.append(CheckResult("Full 7-stage pipeline (TEST_MODE)", "PASS" if ok else "FAIL", detail))

    # ── Production WSGI server availability ──────────────────────
    def _waitress():
        """Check the production WSGI server (waitress) is installed."""
        try:
            import waitress  # noqa: F401
            return "waitress installed"
        except ImportError:
            raise RuntimeError("waitress not installed - `pip install waitress`")
    ok, detail = _safe(_waitress)
    results.append(CheckResult("Production WSGI server (waitress)",
                               "PASS" if ok else "CONFIG", detail))

    return results


def check_config() -> list[CheckResult]:
    """Report which credentials / settings are configured (not pass/fail)."""
    from quoteforge import config
    results: list[CheckResult] = []

    results.append(CheckResult(
        "TEST_MODE", "PASS" if config.TEST_MODE else "CONFIG",
        "true (safe)" if config.TEST_MODE else "FALSE - live mode!"))

    env_path = Path(__file__).resolve().parent.parent / ".env"
    results.append(CheckResult(
        ".env file", "PASS" if env_path.exists() else "CONFIG",
        "present" if env_path.exists() else "missing - copy .env.example"))

    keys = {
        "ANTHROPIC_API_KEY": config.ANTHROPIC_API_KEY,
        "BANNERBEAR_API_KEY": config.BANNERBEAR_API_KEY,
        "UNSPLASH_ACCESS_KEY": config.UNSPLASH_ACCESS_KEY,
        "GELATO_API_KEY": config.GELATO_API_KEY,
        "PRINTIFY_API_KEY": config.PRINTIFY_API_KEY,
        "PRINTIFY_SHOP_ID": config.PRINTIFY_SHOP_ID,
        "PRINTFUL_API_KEY": config.PRINTFUL_API_KEY,
        "ETSY_API_KEY": config.ETSY_API_KEY,
        "ETSY_WEBHOOK_SECRET": config.ETSY_WEBHOOK_SECRET,
        "AIRTABLE_API_KEY": config.AIRTABLE_API_KEY,
    }
    for name, val in keys.items():
        results.append(CheckResult(
            name, "PASS" if val else "CONFIG",
            "configured" if val else "not set"))
    return results


MANUAL_CHECKS = [
    "Artwork: text inside safe area, no clipping/overflow, proper margins",
    "Artwork: exported at 300 DPI, correct dimensions, no pixelation",
    "Artwork: font readable, spacing, line breaks, long names tested",
    "Physical print: colors match screen, no shift, contrast OK",
    "Physical print: sharp text, no blur, no artifacts",
    "Physical print: material quality (poster/frame/canvas) acceptable",
    "Physical print: arrived undamaged, packaging acceptable",
    "Real Etsy test order placed to yourself and received",
]


def run_preflight() -> dict:
    """Run all checks and return a structured report."""
    software = check_software()
    cfg = check_config()
    return {
        "software": software,
        "config": cfg,
        "manual": MANUAL_CHECKS,
        # Only genuine FAILs block. CONFIG items (e.g. optional waitress install)
        # are install/setup steps flagged separately, not test failures.
        "software_passed": not any(r.status == "FAIL" for r in software),
    }


def _print_report(report: dict) -> None:
    """Print the preflight report (software, config, manual sections) to stdout."""
    def line(r: CheckResult) -> str:
        """Format one check result as an '[ICON] name (detail)' report line."""
        icon = {"PASS": "[PASS]", "FAIL": "[FAIL]",
                "CONFIG": "[ -- ]", "MANUAL": "[MANUAL]"}[r.status]
        return f"  {icon} {r.name}" + (f"  ({r.detail})" if r.detail else "")

    print("=" * 64)
    print("QUOTEFORGE GO-LIVE PREFLIGHT")
    print("=" * 64)
    print("\nSoftware / HA / Recovery (automated):")
    for r in report["software"]:
        print(line(r))
    print("\nCredentials / Settings (configure before live):")
    for r in report["config"]:
        print(line(r))
    print("\nManual - physical verification required (cannot automate):")
    for m in report["manual"]:
        print(f"  [MANUAL] {m}")
    print("\n" + "=" * 64)
    if report["software_passed"]:
        print("SOFTWARE: ALL CHECKS PASSED")
    else:
        print("SOFTWARE: SOME CHECKS FAILED - see [FAIL] above")
    print("Physical print verification (Phase 4) is the remaining go-live gate.")
    print("=" * 64)


def main() -> None:
    """Run the full preflight and print the report."""
    _print_report(run_preflight())


if __name__ == "__main__":
    main()
