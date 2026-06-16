"""Source-integrity guard against hallucinated code.

Two fast, deterministic checks that catch the highest-risk classes of mistake
introduced during development:

1. Every module byte-compiles. This catches syntax errors anywhere - most
   importantly a broken edit to the big brace-escaped page f-string in
   listing_preview.py (a wrong `{` vs `{{` is a SyntaxError), which would
   otherwise only surface at rebuild time.
2. The core modules import cleanly. This catches module-level dangling
   references - a call/name/attribute that doesn't actually exist (a
   hallucination) raises NameError/ImportError/AttributeError on import.

If this fails, something references code that isn't there. Fix it before trusting
any "tests pass" claim.
"""
import compileall
import importlib
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent / "quoteforge"

# Core modules we develop against - all import cleanly in the test env today, so
# any new import-time failure is a real regression (a hallucinated reference or a
# bad top-level import), not an environment quirk. GUI modules are excluded: they
# need tkinter, which is absent on headless CI by design.
_CORE_MODULES = [
    "quoteforge.config",
    "quoteforge.preflight",
    "quoteforge.db.database",
    "quoteforge.etsy.listing_preview",
    "quoteforge.etsy.financials",
    "quoteforge.etsy.resolution",
    "quoteforge.etsy.policy",
    "quoteforge.etsy.margin_guard",
    "quoteforge.etsy.shipping_audit",
    "quoteforge.etsy.profit_calculator",
    "quoteforge.etsy.reports",
    "quoteforge.etsy.customer_messages",
    "quoteforge.etsy.delight_loop",
    "quoteforge.etsy.listings",
    "quoteforge.fulfillment.router",
    "quoteforge.fulfillment.claim_service",
    "quoteforge.fulfillment.claim_workflow",
    "quoteforge.fulfillment.gelato_returns",
    "quoteforge.fulfillment.tracking_api",
    "quoteforge.automation.pipeline_orchestrator",
    "quoteforge.automation.order_monitor",
    "quoteforge.automation.autopilot",
    "quoteforge.automation.fulfillment_tracker",
    "quoteforge.automation.gelato_api",
    "quoteforge.automation.full_backup",
    "quoteforge.automation.upsell",
    "quoteforge.automation.emailer",
    "quoteforge.automation.google_drive_client",
    "quoteforge.automation.webhook_server",
    "quoteforge.analytics.financial_reports",
    "quoteforge.ai.ange",
    "quoteforge.admin",
]


def test_all_source_byte_compiles():
    # quiet=1 suppresses progress output but still reports failures; returns True
    # only if every .py under quoteforge/ compiles.
    ok = compileall.compile_dir(str(_PKG), quiet=1, force=True)
    assert ok, "A module under quoteforge/ failed to byte-compile (syntax error)."


def test_core_modules_import_cleanly():
    failures = []
    for mod in _CORE_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 - we want to report ANY import failure
            failures.append(f"{mod}: {type(exc).__name__}: {exc}")
    assert not failures, "Modules failed to import (dangling reference?):\n" + "\n".join(failures)
