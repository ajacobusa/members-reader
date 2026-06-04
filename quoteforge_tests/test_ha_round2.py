"""Round-two HA/performance fixes: async webhook dispatch, deep health check,
broadened transient-error retry (Claude 429/529/5xx), non-blocking tracking."""
import time
from unittest.mock import patch, MagicMock

import pytest


# ── Broadened transient classification (Anthropic SDK shapes) ────

def test_is_transient_direct_status_code():
    from quoteforge.automation.retry import is_transient
    e = Exception("overloaded")
    e.status_code = 529  # Anthropic "overloaded"
    assert is_transient(e) is True


def test_is_transient_rate_limit_by_name():
    from quoteforge.automation.retry import is_transient

    class RateLimitError(Exception):
        pass

    class InternalServerError(Exception):
        pass

    class OverloadedError(Exception):
        pass

    assert is_transient(RateLimitError()) is True
    assert is_transient(InternalServerError()) is True
    assert is_transient(OverloadedError()) is True


def test_is_transient_rejects_value_error():
    from quoteforge.automation.retry import is_transient
    assert is_transient(ValueError("bad input")) is False


def test_retry_recovers_from_anthropic_overload():
    from quoteforge.automation.retry import retry_call

    calls = {"n": 0}

    class OverloadedError(Exception):
        def __init__(self):
            self.status_code = 529

    def flaky_quote():
        calls["n"] += 1
        if calls["n"] < 2:
            raise OverloadedError()
        return ["A heartfelt message."]

    with patch("quoteforge.automation.retry.time.sleep"):
        result = retry_call(flaky_quote, max_attempts=3, base_delay=0.01)
    assert result == ["A heartfelt message."]
    assert calls["n"] == 2


# ── Async webhook dispatch (202 Accepted, no blocking) ───────────

def _client(tmp_path):
    """Build a Flask test client with isolated DB + output dirs."""
    import quoteforge.automation.webhook_server as ws
    ws.OUTPUT_DIR = tmp_path
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.OUTPUT_DIR", tmp_path):
        ws.app.config["TESTING"] = True
        yield ws.app.test_client()


@pytest.fixture
def client(tmp_path):
    yield from _client(tmp_path)


def test_order_returns_202_immediately(client):
    resp = client.post("/order", json={
        "recipient_name": "Emma", "occasion": "Graduation",
        "order_id": "ASYNC-1", "customer_name": "Jen",
    })
    assert resp.status_code == 202
    assert resp.get_json()["status"] == "accepted"
    # let the background thread finish so it doesn't leak into other tests
    time.sleep(0.5)


def test_order_missing_fields_returns_400(client):
    resp = client.post("/order", json={"customer_name": "Jen"})
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_duplicate_returns_200_not_400(client):
    payload = {"recipient_name": "Emma", "occasion": "Graduation",
               "order_id": "DUP-200", "customer_name": "Jen"}
    first = client.post("/order", json=payload)
    assert first.status_code == 202
    time.sleep(0.6)  # let the first order persist
    second = client.post("/order", json=payload)
    assert second.status_code == 200  # NOT 400 — sender must not retry
    assert second.get_json()["status"] == "duplicate"


# ── Deep health check ────────────────────────────────────────────

def test_health_reports_db_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


# ── Non-blocking tracking update ─────────────────────────────────

def test_check_and_update_tracking(tmp_path):
    with patch("quoteforge.db.database.DB_PATH", tmp_path / "t.db"), \
         patch("quoteforge.db.database.OUTPUT_DIR", tmp_path):
        from quoteforge.db.database import init_db, create_order, get_order
        from quoteforge.automation import gelato_api
        init_db()
        oid = create_order({"order_id": "TRK-1", "recipient_name": "X", "occasion": "Y"})

        fake_status = {"gelato_order_id": "G-1", "status": "shipped",
                       "tracking_number": "1Z999", "tracking_url": "http://t"}
        with patch.object(gelato_api, "get_gelato_order_status", return_value=fake_status):
            result = gelato_api.check_and_update_tracking(oid, "G-1")
        order = get_order(oid)
    assert result["tracking_number"] == "1Z999"
    assert order["tracking_number"] == "1Z999"
    assert order["status"] == "shipped"
