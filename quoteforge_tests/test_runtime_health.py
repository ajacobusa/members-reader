"""Runtime/environment health agent - the infra-review agent's watch over the
daemons, ports, worker processes, hooks and plugins the toolchain depends on.

All deterministic: settings/plugin paths and the port probe are injected, so these
never touch the real ~/.claude or open a real socket.
"""
import json

import quoteforge.automation.runtime_health as rh


def _settings(tmp_path, enabled):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"enabledPlugins": {"claude-mem@thedotmack": enabled}}),
                 encoding="utf-8")
    return p


def _plugins(tmp_path, with_deps, version="13.8.1"):
    pdir = tmp_path / "plugins" / "cache" / "thedotmack" / "claude-mem" / version
    pdir.mkdir(parents=True)
    if with_deps:
        (pdir / "node_modules").mkdir()
    return tmp_path / "plugins"


# ───────────────────────────────────────── claude-mem worker (the known issue)
def test_claude_mem_skips_without_config(tmp_path):
    c = rh.check_claude_mem(settings_path=tmp_path / "none.json",
                            plugins_root=tmp_path / "plugins")
    assert c["ok"] and c["skipped"]


def test_claude_mem_skips_when_disabled(tmp_path):
    c = rh.check_claude_mem(_settings(tmp_path, False), _plugins(tmp_path, True))
    assert c["ok"] and c["skipped"]


def test_claude_mem_FAILS_when_enabled_but_deps_missing(tmp_path):
    # The exact failure this session hit: enabled, but node_modules never installed.
    c = rh.check_claude_mem(_settings(tmp_path, True),
                            _plugins(tmp_path, with_deps=False),
                            port_probe=lambda p: True)
    assert c["ok"] is False and "deps MISSING" in c["detail"]


def test_claude_mem_FAILS_when_worker_port_down(tmp_path):
    c = rh.check_claude_mem(_settings(tmp_path, True),
                            _plugins(tmp_path, with_deps=True),
                            port_probe=lambda p: False)
    assert c["ok"] is False and "NOT listening" in c["detail"]


def test_claude_mem_ok_when_enabled_deps_and_port(tmp_path):
    c = rh.check_claude_mem(_settings(tmp_path, True),
                            _plugins(tmp_path, with_deps=True),
                            port_probe=lambda p: True)
    assert c["ok"] and not c["skipped"]


# ───────────────────────────────────────── ports
def test_required_ports_skip_when_none():
    assert rh.check_required_ports(ports=[], port_probe=lambda p: False)["ok"]


def test_required_ports_fail_when_down_and_ok_when_up():
    down = rh.check_required_ports(ports=[("worker", 9)], port_probe=lambda p: False)
    assert down["ok"] is False and "9" in down["detail"]
    assert rh.check_required_ports(ports=[("worker", 9)], port_probe=lambda p: True)["ok"]


# ───────────────────────────────────────── hooks (an enabled plugin's down worker
#                                            blocks the IDE)
def test_hooks_flag_a_down_worker_backed_plugin(tmp_path):
    c = rh.check_hooks(_settings(tmp_path, True), _plugins(tmp_path, with_deps=False))
    assert c["ok"] is False


def test_hooks_skip_when_no_worker_plugin(tmp_path):
    c = rh.check_hooks(_settings(tmp_path, False), _plugins(tmp_path, True))
    assert c["ok"] and c["skipped"]


# ───────────────────────────────────────── issue registry + aggregate
def test_known_issues_registry_tracks_claude_mem():
    assert any(i["id"] == "claude-mem-worker-deps" for i in rh.load_known_issues())


def test_runtime_health_aggregate_fails_on_broken_plugin(tmp_path):
    r = rh.check_runtime_health(_settings(tmp_path, True),
                               _plugins(tmp_path, with_deps=False),
                               port_probe=lambda p: True)
    assert r["ok"] is False
    assert any(i["id"] == "claude-mem-worker-deps" for i in r["open_issues"])


def test_runtime_health_aggregate_ok_when_disabled(tmp_path):
    r = rh.check_runtime_health(_settings(tmp_path, False),
                               _plugins(tmp_path, with_deps=True),
                               port_probe=lambda p: True)
    assert r["ok"] is True


# ───────────────────────────────────────── wired into the infra-review agent
def test_infra_check_includes_runtime_health():
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    assert "runtime_health" in {c["name"] for c in r["checks"]}


def test_infra_check_runtime_health_catches_degradation(monkeypatch):
    # GROUNDING: a degraded runtime (down worker) must flip the infra-check agent red.
    import quoteforge.automation.runtime_health as rhmod
    from quoteforge.automation.infra_check import check_infrastructure
    monkeypatch.setattr(rhmod, "check_runtime_health", lambda: {
        "ok": False,
        "checks": [{"name": "claude_mem_worker", "ok": False, "detail": "down",
                    "skipped": False}],
        "open_issues": []})
    r = check_infrastructure()
    c = next(c for c in r["checks"] if c["name"] == "runtime_health")
    assert c["ok"] is False and r["ok"] is False
