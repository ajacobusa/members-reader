"""Production-readiness tracker.

You're running locally for UAT; this records the current state of every
environment-dependent setting and exactly what to change when you move to the
permanent server. `format_text()` prints it; `write_migration_doc()` regenerates
docs/PRODUCTION_MIGRATION.md so the move-to-server checklist always reflects the
live state (keeps track of future changes automatically).
"""
from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path


def _has(env: str) -> bool:
    return bool(os.getenv(env, "").strip())


def readiness() -> dict:
    """Each item: name, status (ready|todo|optional), current, action."""
    from quoteforge import config as cfg
    items = []

    def add(name, status, current, action):
        items.append({"name": name, "status": status,
                      "current": current, "action": action})

    # TEST_MODE must be OFF in production
    add("TEST_MODE", "ready" if not cfg.TEST_MODE else "todo",
        f"{cfg.TEST_MODE}",
        "Set TEST_MODE=false on the server so real Etsy/Gelato/Claude calls run.")

    # Print-file hosting (so Gelato can fetch customer photos)
    try:
        from quoteforge.automation.file_host import active_backend
        b = active_backend()
        add("Print-file hosting", "ready" if b["public"] else "todo", b["detail"],
            "Set Google Drive (GOOGLE_DRIVE_FOLDER_ID + GOOGLE_SERVICE_ACCOUNT_FILE) "
            "or PUBLIC_FILE_DIR + PUBLIC_FILE_BASE_URL so uploaded JPGs are fetchable.")
    except Exception:  # noqa: BLE001
        add("Print-file hosting", "todo", "unknown", "Configure a public file host.")

    # Server URL the static site calls (Ask Ange / signup / upload / A-B)
    add("Server API URL (ASK_ANGE_API_URL)",
        "ready" if cfg.ASK_ANGE_API_URL else "todo",
        cfg.ASK_ANGE_API_URL or "(not set - widgets degrade gracefully)",
        "Host the webhook server (Render/own box) and set ASK_ANGE_API_URL to its "
        "/ask URL so Ask Ange, signup, photo upload, and A/B all work live.")

    # Core API keys
    add("Claude API (ANTHROPIC_API_KEY)", "ready" if _has("ANTHROPIC_API_KEY") else "todo",
        "set" if _has("ANTHROPIC_API_KEY") else "missing",
        "Set ANTHROPIC_API_KEY for AI quote/vision/quality features.")
    add("Gelato (GELATO_API_KEY)", "ready" if _has("GELATO_API_KEY") else "todo",
        "set" if _has("GELATO_API_KEY") else "missing",
        "Set GELATO_API_KEY to place real print orders.")
    add("Etsy (ETSY_API_KEY)", "ready" if _has("ETSY_API_KEY") else "todo",
        "set" if _has("ETSY_API_KEY") else "missing",
        "Set ETSY_API_KEY + token for order polling, tracking push, competitor pulls.")

    # Reports / analytics (optional but recommended)
    add("Report recipient", "ready" if cfg.REPORT_RECIPIENT else "todo",
        cfg.REPORT_RECIPIENT or "(unset)",
        "Confirm REPORT_RECIPIENT is your email for daily/Friday reports.")
    add("Google Analytics (GA_MEASUREMENT_ID)",
        "ready" if cfg.GA_MEASUREMENT_ID else "optional",
        cfg.GA_MEASUREMENT_ID or "(unset)", "Optional: set for GA traffic stats.")
    add("Clarity (CLARITY_PROJECT_ID/API)",
        "ready" if cfg.CLARITY_PROJECT_ID else "optional",
        cfg.CLARITY_PROJECT_ID or "(unset)",
        "Optional: set CLARITY_PROJECT_ID + CLARITY_API_TOKEN for heatmaps/rage clicks.")
    add("Pinterest (PINTEREST_ACCESS_TOKEN)",
        "ready" if _has("PINTEREST_ACCESS_TOKEN") else "optional",
        "set" if _has("PINTEREST_ACCESS_TOKEN") else "(unset)",
        "Optional: set to auto-publish pins + enrich trend predictions.")
    add("Competitors tracked", "ready" if cfg.COMPETITORS else "optional",
        ", ".join(cfg.COMPETITORS) or "(none)",
        "Optional: set COMPETITORS to track rival prices/listings.")
    add("Output dir", "ready", str(cfg.OUTPUT_DIR),
        "On the server, point OUTPUT_DIR at persistent storage (not ephemeral).")

    todo = [i for i in items if i["status"] == "todo"]
    return {"items": items, "todo": todo,
            "ready_for_production": not todo,
            "generated_at": datetime.now().isoformat()}


def format_text(state: dict | None = None) -> str:
    s = state or readiness()
    icon = {"ready": "[OK]  ", "todo": "[TODO]", "optional": "[opt] "}
    lines = ["Production Readiness - move-to-server tracker", "=" * 52,
             f"  Ready for production: {s['ready_for_production']} "
             f"({len(s['todo'])} required item(s) left)", ""]
    for i in s["items"]:
        lines.append(f"{icon.get(i['status'], '      ')} {i['name']}: {i['current']}")
        if i["status"] == "todo":
            lines.append(f"        -> {i['action']}")
    return "\n".join(lines)


def write_migration_doc(path: str | None = None) -> str:
    """Regenerate docs/PRODUCTION_MIGRATION.md from the current state."""
    from quoteforge.config import OUTPUT_DIR  # noqa: F401
    s = readiness()
    dest = Path(path) if path else (Path(__file__).resolve().parents[2]
                                    / "docs" / "PRODUCTION_MIGRATION.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Production Migration Tracker",
             "",
             f"_Auto-generated {s['generated_at']}. Running locally for UAT; this "
             "lists what to change when moving to the permanent server._",
             "",
             f"**Ready for production:** {'YES' if s['ready_for_production'] else 'NO'} "
             f"- {len(s['todo'])} required item(s) remaining.",
             "",
             "## Required before go-live", ""]
    todo = [i for i in s["items"] if i["status"] == "todo"]
    if todo:
        for i in todo:
            lines.append(f"- [ ] **{i['name']}** (now: `{i['current']}`) - {i['action']}")
    else:
        lines.append("- [x] All required items configured.")
    lines += ["", "## Full environment state", "",
              "| Setting | Status | Current | Production action |",
              "|---|---|---|---|"]
    for i in s["items"]:
        lines.append(f"| {i['name']} | {i['status']} | {i['current']} | {i['action']} |")
    lines += ["", "## Move-to-server steps (summary)", "",
              "1. Provision the permanent server (Render/own box); deploy the webhook "
              "server (see docs/DEPLOY.md).",
              "2. Set the env vars flagged TODO above.",
              "3. Point OUTPUT_DIR at persistent storage; restore the latest DB backup.",
              "4. Set ASK_ANGE_API_URL to the live server `/ask` URL and rebuild the "
              "site so the storefront talks to production.",
              "5. Install the scheduled jobs on the server (`admin install-schedule`).",
              "6. Run `admin deploy-status` and `admin healthcheck` to confirm green.",
              ""]
    dest.write_text("\n".join(lines), encoding="utf-8")
    return str(dest)
