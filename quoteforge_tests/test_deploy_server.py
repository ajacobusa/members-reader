"""Tests for hosting: WSGI app, /health, /ask, PORT + OUTPUT_DIR env."""
import os


def test_wsgi_app_importable():
    import wsgi
    assert wsgi.app is not None


def test_health_and_ask_routes(monkeypatch, tmp_path):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.automation.webhook_server import app
    c = app.test_client()
    h = c.get("/health")
    assert h.status_code in (200, 503)
    a = c.post("/ask", json={"q": "is the frame included?"})
    assert a.status_code == 200
    body = a.get_json()
    assert "answer" in body and "frame" in body["answer"].lower()
    assert a.headers.get("Access-Control-Allow-Origin") == "*"


def test_port_env_used(monkeypatch):
    import quoteforge.automation.webhook_server as ws
    calls = {}
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setattr(ws, "FLASK_AVAILABLE", True, raising=False)
    # capture the port waitress would bind without actually serving
    import sys, types
    fake = types.ModuleType("waitress")
    fake.serve = lambda app, host, port, threads: calls.update(port=port)
    monkeypatch.setitem(sys.modules, "waitress", fake)
    ws.run_server()
    assert calls.get("port") == 8123
