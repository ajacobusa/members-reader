"""Runtime / environment health agent - the infra-review agent's proactive watch
over the DAEMONS, PORTS, WORKER PROCESSES, HOOKS and PLUGINS the toolchain depends
on, plus a registry of known infrastructure issues.

Why this exists: a plugin can be ENABLED while its backing worker daemon is down,
and its PreToolUse hooks then BLOCK the IDE's own Read/Edit tools - a silent,
infuriating failure (this is exactly what claude-mem did: it shipped without its
node_modules, so the worker could never start and every hook reported 'unreachable'
and blocked editing). The code-invariant checks in infra_check never see that. This
module catches that class of failure PROACTIVELY: it verifies the worker's deps are
installed and its port answers BEFORE the hook blocks anything.

GROUNDED + SKIP-FRIENDLY: every check reads the real environment (settings.json,
node_modules on disk, a TCP connect to the port) and returns ok=True with a
``skipped`` flag when its component isn't present - so the PRODUCTION infra-check
(Render, where the dev-time Claude Code plugins/hooks don't exist) stays clean,
while a LOCAL run catches the dev-environment problems. Every check fails CLOSED on
an unexpected error. Paths/probes are injectable so tests never touch the real env.
"""
from __future__ import annotations

import json
import logging
import socket
from pathlib import Path

logger = logging.getLogger(__name__)

# The claude-mem plugin's worker daemon listens here; its hooks block the IDE when
# it's down. Centralised so the port check and the worker check agree.
_CLAUDE_MEM_PORT = 37777


def _h(name: str, ok: bool, detail: str, *, skipped: bool = False) -> dict:
    """One runtime-health result. `skipped` means 'not applicable here' (still ok)."""
    return {"name": name, "ok": bool(ok), "detail": detail, "skipped": skipped}


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """True iff a TCP connect to host:port succeeds (a daemon is listening)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _claude_config_dir() -> Path:
    """The Claude Code config dir (CLAUDE_CONFIG_DIR, else ~/.claude)."""
    import os
    return Path(os.getenv("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


def _issues_path() -> Path:
    """The committed registry of tracked infrastructure issues."""
    return Path(__file__).resolve().parent / "known_issues.json"


def load_known_issues() -> list:
    """Tracked infrastructure issues (id/title/severity/status/remediation). []
    if the registry is absent or unreadable."""
    p = _issues_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")) or []
        except Exception as exc:  # noqa: BLE001
            logger.debug("known_issues.json unreadable: %s", exc)
    return []


def _resolve_plugin_dir(plugins_root: Path, vendor: str, name: str) -> "Path | None":
    """The newest installed plugin dir the hooks would use (cache/<vendor>/<name>/
    <version>[/plugin]), or None if not installed."""
    cache = plugins_root / "cache" / vendor / name
    if not cache.exists():
        return None
    versions = sorted((p for p in cache.glob("*") if p.is_dir()),
                      key=lambda p: p.name, reverse=True)
    if not versions:
        return None
    top = versions[0]
    return (top / "plugin") if (top / "plugin" / "scripts").is_dir() else top


def check_claude_mem(settings_path=None, plugins_root=None, port_probe=_port_open) -> dict:
    """Health of the claude-mem plugin worker. If the plugin is ENABLED, its
    node_modules must be installed (else the worker can't start) AND its worker
    daemon must answer on its port (else its PreToolUse hooks BLOCK the IDE's
    Read/Edit). Skips cleanly when Claude Code / the plugin isn't present."""
    cfg = _claude_config_dir()
    settings_path = Path(settings_path) if settings_path else cfg / "settings.json"
    plugins_root = Path(plugins_root) if plugins_root else cfg / "plugins"
    try:
        if not settings_path.exists():
            return _h("claude_mem_worker", True, "skipped (no Claude Code config)",
                      skipped=True)
        enabled = (json.loads(settings_path.read_text(encoding="utf-8"))
                   .get("enabledPlugins", {}).get("claude-mem@thedotmack"))
        if not enabled:
            return _h("claude_mem_worker", True, "claude-mem disabled (inactive)",
                      skipped=True)
        pdir = _resolve_plugin_dir(plugins_root, "thedotmack", "claude-mem")
        if pdir is None:
            return _h("claude_mem_worker", True, "skipped (plugin not installed)",
                      skipped=True)
        if not (pdir / "node_modules").is_dir():
            return _h("claude_mem_worker", False,
                      f"ENABLED but worker deps MISSING ({pdir.name}/node_modules) - "
                      "the worker can't start and its hooks will BLOCK Read/Edit. Fix: "
                      "`npx claude-mem repair` + `bun install` in the plugin dir.")
        if not port_probe(_CLAUDE_MEM_PORT):
            return _h("claude_mem_worker", False,
                      f"ENABLED + deps present but worker NOT listening on "
                      f"{_CLAUDE_MEM_PORT} - hooks may block the IDE. Fix: restart "
                      "Claude Code or `npx claude-mem start`.")
        return _h("claude_mem_worker", True,
                  f"enabled, deps present, worker responding on {_CLAUDE_MEM_PORT}")
    except Exception as exc:  # noqa: BLE001 - fail closed
        return _h("claude_mem_worker", False, f"check errored: {exc}")


def expected_ports(settings_path=None, plugins_root=None) -> list:
    """The (name, port) daemons that SHOULD be listening given what's active here.
    Derived from real state so we never alarm on a port whose owner isn't enabled."""
    cfg = _claude_config_dir()
    settings_path = Path(settings_path) if settings_path else cfg / "settings.json"
    plugins_root = Path(plugins_root) if plugins_root else cfg / "plugins"
    ports: list = []
    try:
        if settings_path.exists():
            en = (json.loads(settings_path.read_text(encoding="utf-8"))
                  .get("enabledPlugins", {}))
            if en.get("claude-mem@thedotmack") and _resolve_plugin_dir(
                    plugins_root, "thedotmack", "claude-mem"):
                ports.append(("claude-mem worker", _CLAUDE_MEM_PORT))
    except Exception as exc:  # noqa: BLE001
        logger.debug("expected_ports: %s", exc)
    return ports


def check_required_ports(ports=None, port_probe=_port_open) -> dict:
    """Every daemon port that should be listening is. Skips when none are expected
    (e.g. on a host with no worker-backed plugins enabled)."""
    ports = ports if ports is not None else expected_ports()
    if not ports:
        return _h("required_ports", True, "skipped (no daemon ports expected)",
                  skipped=True)
    down = [f"{n}:{p}" for (n, p) in ports if not port_probe(p)]
    return _h("required_ports", not down,
              f"all {len(ports)} daemon port(s) listening" if not down
              else f"NOT listening: {down}")


def check_hooks(settings_path=None, plugins_root=None) -> dict:
    """The IDE hooks are sane: settings.json parses, and no ENABLED plugin's hooks
    are backed by a DOWN worker (which would block the IDE's tools). The
    worker-backed plugin we know about is claude-mem; delegate to its check."""
    cfg = _claude_config_dir()
    settings_path = Path(settings_path) if settings_path else cfg / "settings.json"
    try:
        if not settings_path.exists():
            return _h("hooks_not_blocking", True, "skipped (no Claude Code config)",
                      skipped=True)
        json.loads(settings_path.read_text(encoding="utf-8"))   # parses?
    except Exception as exc:  # noqa: BLE001
        return _h("hooks_not_blocking", False, f"settings.json unreadable: {exc}")
    cm = check_claude_mem(settings_path, plugins_root)
    if cm["skipped"]:
        return _h("hooks_not_blocking", True, "no worker-backed plugin hooks active",
                  skipped=True)
    return _h("hooks_not_blocking", cm["ok"],
              "no enabled-plugin hook is backed by a down worker" if cm["ok"]
              else f"a plugin hook's worker is down -> may block the IDE: {cm['detail']}")


def check_runtime_health(settings_path=None, plugins_root=None,
                         port_probe=_port_open) -> dict:
    """Aggregate runtime/environment health: worker daemons, required ports, hooks,
    plus the open tracked issues. {ok, checks:[...], open_issues:[...]}."""
    checks = [
        check_claude_mem(settings_path, plugins_root, port_probe),
        check_required_ports(expected_ports(settings_path, plugins_root), port_probe),
        check_hooks(settings_path, plugins_root),
    ]
    open_issues = [i for i in load_known_issues()
                   if str(i.get("status", "")).lower() not in ("resolved", "closed")]
    return {"ok": all(c["ok"] for c in checks), "checks": checks,
            "open_issues": open_issues}


def format_runtime_health_text(result: dict) -> str:
    """Human-readable runtime-health report."""
    lines = ["Runtime / environment health", "=" * 56]
    for c in result["checks"]:
        icon = "[skip]" if c.get("skipped") else ("[OK]  " if c["ok"] else "[FAIL]")
        lines.append(f"  {icon} {c['name']}: {c['detail']}")
    issues = result.get("open_issues", [])
    lines.append("")
    lines.append(f"Tracked infrastructure issues (open: {len(issues)}):")
    for i in issues:
        lines.append(f"  - [{i.get('severity', '?')}/{i.get('status', '?')}] "
                     f"{i.get('id', '?')}: {i.get('title', '')}")
        if i.get("remediation"):
            lines.append(f"      fix: {i['remediation']}")
    if not issues:
        lines.append("  (none)")
    return "\n".join(lines)
