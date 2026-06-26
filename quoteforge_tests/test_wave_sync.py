"""Wave accounting API integration: key-gated client + per-order payout sync.
All network is mocked - no live token, TEST_MODE-safe.
"""
import sqlite3

import pytest


def _cfg(monkeypatch, **kw):
    import quoteforge.config as c
    monkeypatch.setattr(c, "TEST_MODE", kw.get("test_mode", False))
    monkeypatch.setattr(c, "WAVE_API_TOKEN", kw.get("token", "tok"))
    monkeypatch.setattr(c, "WAVE_BUSINESS_ID", kw.get("bid", "B1"))
    monkeypatch.setattr(c, "WAVE_ACCT_BANK", kw.get("bank", "ACC_BANK"))
    monkeypatch.setattr(c, "WAVE_ACCT_SALES", kw.get("sales", "ACC_SALES"))
    monkeypatch.setattr(c, "WAVE_ACCT_SHIPPING", kw.get("ship", "ACC_SHIP"))
    monkeypatch.setattr(c, "WAVE_ACCT_FEES", kw.get("fees", "ACC_FEES"))


def test_not_configured_is_safe(monkeypatch):
    import quoteforge.config as c
    monkeypatch.setattr(c, "WAVE_API_TOKEN", "")
    from quoteforge.etsy import wave_api
    assert wave_api.list_businesses() == []
    r = wave_api.create_money_transaction("B", "x", "2026-06-01", "d", {}, [])
    assert r["ok"] is False


def test_test_mode_never_calls_network(monkeypatch):
    import quoteforge.config as c, quoteforge.etsy.wave_api as w, requests
    monkeypatch.setattr(c, "WAVE_API_TOKEN", "tok")
    monkeypatch.setattr(c, "TEST_MODE", True)
    called = {"n": 0}
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    assert w._post("query{}") is None and called["n"] == 0


def test_list_businesses_and_accounts(monkeypatch):
    _cfg(monkeypatch)
    import quoteforge.etsy.wave_api as w, requests

    def fake_post(url, headers=None, json=None, timeout=None):
        q = json["query"]

        class R:
            status_code = 200

            @staticmethod
            def json():
                if "businesses" in q:
                    return {"data": {"businesses": {"edges": [{"node": {
                        "id": "B1", "name": "Joffiels",
                        "currency": {"code": "USD"}}}]}}}
                return {"data": {"business": {"accounts": {"edges": [{"node": {
                    "id": "ACC_BANK", "name": "Checking",
                    "type": {"value": "ASSET"},
                    "subtype": {"value": "CASH_AND_BANK"}}}]}}}}
        return R()
    monkeypatch.setattr(requests, "post", fake_post)
    b = w.list_businesses()
    assert b and b[0]["id"] == "B1" and b[0]["currency"] == "USD"
    a = w.list_accounts("B1")
    assert a and a[0]["id"] == "ACC_BANK" and a[0]["type"] == "ASSET"


def test_create_transaction_success_then_error(monkeypatch):
    _cfg(monkeypatch)
    import quoteforge.etsy.wave_api as w, requests
    state = {"ok": True}

    def fake_post(url, headers=None, json=None, timeout=None):
        class R:
            status_code = 200

            @staticmethod
            def json():
                if state["ok"]:
                    return {"data": {"moneyTransactionCreate": {
                        "didSucceed": True, "inputErrors": None,
                        "transaction": {"id": "T1"}}}}
                return {"data": {"moneyTransactionCreate": {
                    "didSucceed": False,
                    "inputErrors": [{"code": "BAD", "message": "bad account",
                                     "path": ["x"]}], "transaction": None}}}
        return R()
    monkeypatch.setattr(requests, "post", fake_post)
    ok = w.create_money_transaction(
        "B1", "e1", "2026-06-01", "d",
        {"accountId": "ACC_BANK", "amount": 10, "direction": "DEPOSIT"}, [])
    assert ok["ok"] and ok["id"] == "T1"
    state["ok"] = False
    bad = w.create_money_transaction("B1", "e1", "2026-06-01", "d", {}, [])
    assert bad["ok"] is False and "BAD" in bad["errors"][0]


@pytest.fixture
def db(tmp_path, monkeypatch):
    import quoteforge.db.database as d
    monkeypatch.setattr(d, "DB_PATH", tmp_path / "t.db")
    d.init_db()
    return d


def _insert(d, oid, status, sale, **extra):
    conn = sqlite3.connect(d.DB_PATH)
    cols = {"order_id": oid, "recipient_name": "R", "occasion": "birthday",
            "status": status, "sale_price": sale, "created_at": "2026-06-12",
            "gelato_cost": 13.0, "tax_collected": 3.20, "shipping_collected": 5.0,
            "etsy_fees_actual": 2.60, **extra}
    conn.execute(f"INSERT INTO orders ({','.join(cols)}) "
                 f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
    conn.commit()
    conn.close()


def test_sync_builds_balanced_transaction(db, monkeypatch):
    _cfg(monkeypatch)
    _insert(db, "E1", "shipped", 43.20)
    from quoteforge.etsy.wave_sync import sync_period
    res = sync_period("month", dry_run=True)
    assert res["orders"] == 1 and res["missing_config"] == []
    t = res["txns"][0]
    # Etsy order: product_revenue 40 (item+ship, tax excl); fees 2.60; net 37.40
    assert t["anchor"]["amount"] == 37.40 and t["anchor"]["direction"] == "DEPOSIT"
    sales = [li for li in t["lineItems"] if li["accountId"] == "ACC_SALES"][0]["amount"]
    fees = [li for li in t["lineItems"] if li["accountId"] == "ACC_FEES"][0]["amount"]
    assert round(sales - fees, 2) == t["anchor"]["amount"]      # balances
    assert t["externalId"] == "joffiels-E1"                     # idempotent ref


def test_sync_missing_config_blocks_live(db, monkeypatch):
    _cfg(monkeypatch, bank="")          # no anchor account
    _insert(db, "E1", "shipped", 43.20)
    from quoteforge.etsy.wave_sync import sync_period
    res = sync_period("month", dry_run=False)
    assert "WAVE_ACCT_BANK" in res["missing_config"] and res["created"] == 0


def test_sync_live_pushes(db, monkeypatch):
    _cfg(monkeypatch)
    _insert(db, "E1", "shipped", 43.20)
    import quoteforge.etsy.wave_sync as ws
    monkeypatch.setattr("quoteforge.etsy.wave_api.create_money_transaction",
                        lambda *a, **k: {"ok": True, "id": "T1", "errors": []})
    res = ws.sync_period("month", dry_run=False)
    assert res["created"] == 1 and res["failed"] == 0
