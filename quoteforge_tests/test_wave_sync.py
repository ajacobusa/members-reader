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
    monkeypatch.setattr(c, "WAVE_ACCT_SALES", "ACC_SALES")
    monkeypatch.setattr(c, "WAVE_ACCT_SHIPPING", "ACC_SHIP")
    monkeypatch.setattr(c, "WAVE_ACCT_FEES", "ACC_FEES")
    monkeypatch.setattr(c, "WAVE_ACCT_COGS", "ACC_COGS")
    monkeypatch.setattr(c, "WAVE_ACCT_INFRA", "ACC_INFRA")
    monkeypatch.setattr(c, "WAVE_ACCT_TAX", "ACC_TAX")
    monkeypatch.setattr(c, "WAVE_AUTO_SYNC", kw.get("auto", False))
    monkeypatch.setattr(c, "USE_MAKE_COM", False, raising=False)
    monkeypatch.setattr(c, "MONTHLY_FIXED_COSTS", 0.0, raising=False)


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
    from datetime import datetime
    conn = sqlite3.connect(d.DB_PATH)
    _cm = datetime.now().strftime("%Y-%m-%d")            # TODAY (current month, not future)
    cols = {"order_id": oid, "recipient_name": "R", "occasion": "birthday",
            "status": status, "sale_price": sale, "created_at": _cm,
            "gelato_cost": 13.0, "tax_collected": 3.20, "shipping_collected": 5.0,
            "etsy_fees_actual": 2.60, **extra}
    conn.execute(f"INSERT INTO orders ({','.join(cols)}) "
                 f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
    conn.commit()
    conn.close()


def test_sync_pushes_every_cost_line(db, monkeypatch):
    # REGRESSION: the push covers ALL costs (sales, fees, COGS) + the tax pair, each
    # as a categorized one-line transaction.
    _cfg(monkeypatch)
    _insert(db, "E1", "shipped", 43.20)         # tax_collected 3.20 -> tax pair
    from quoteforge.etsy.wave_sync import sync_period
    res = sync_period("month", dry_run=True)
    assert res["missing_config"] == [] and res["lines"] >= 5
    by = {}
    for t in res["txns"]:
        by.setdefault(t["account"], []).append(t)
    # income -> DEPOSIT to sales (tax-exclusive product revenue 40.00)
    assert by["sales"][0]["anchor"]["direction"] == "DEPOSIT"
    assert by["sales"][0]["anchor"]["amount"] == 40.00
    # Gelato COGS + Etsy fees -> WITHDRAWAL
    assert by["cogs"][0]["anchor"]["direction"] == "WITHDRAWAL"
    assert by["fees"][0]["anchor"]["direction"] == "WITHDRAWAL"
    # tax pass-through PAIR with a DECREASE (remittance) line, nets to $0
    tax = by["tax"]
    assert len(tax) == 2
    assert any(t["lineItems"][0]["balance"] == "DECREASE" for t in tax)
    assert all(t["externalId"].startswith("joffiels-") for t in res["txns"])


def test_sync_missing_config_blocks_live(db, monkeypatch):
    _cfg(monkeypatch, bank="")          # no anchor account
    _insert(db, "E1", "shipped", 43.20)
    from quoteforge.etsy.wave_sync import sync_period
    res = sync_period("month", dry_run=False)
    assert "WAVE_ACCT_BANK" in res["missing_config"] and res["created"] == 0


def test_sync_live_pushes_all_lines(db, monkeypatch):
    _cfg(monkeypatch)
    _insert(db, "E1", "shipped", 43.20)
    import quoteforge.etsy.wave_sync as ws
    monkeypatch.setattr("quoteforge.etsy.wave_api.create_money_transaction",
                        lambda *a, **k: {"ok": True, "id": "T", "errors": []})
    res = ws.sync_period("month", dry_run=False)
    assert res["created"] == res["lines"] and res["failed"] == 0


def test_wave_sync_email_is_dry_run_review(db, monkeypatch):
    # `wave-sync month email` emails a DRY-RUN review and NEVER pushes.
    _cfg(monkeypatch)
    _insert(db, "E1", "shipped", 43.20)
    import quoteforge.automation.emailer as em
    import quoteforge.etsy.wave_api as w
    seen = {}
    monkeypatch.setattr(em, "_send_email",
                        lambda subj, body, to="", attachments=None: seen.update(
                            to=to, body=body) or {"status": "sent", "to": to})
    pushed = {"n": 0}
    monkeypatch.setattr(w, "create_money_transaction",
                        lambda *a, **k: pushed.__setitem__("n", pushed["n"] + 1))
    from quoteforge import admin
    rc = admin.main(["wave-sync", "month", "email"])
    assert rc == 0 and pushed["n"] == 0 and "DRY-RUN" in seen["body"]


def test_auto_pushes_only_when_flag_enabled(db, monkeypatch):
    # REGRESSION: `wave-sync --auto` pushes live ONLY when WAVE_AUTO_SYNC is on.
    _cfg(monkeypatch, auto=False)
    _insert(db, "E1", "shipped", 43.20)
    import quoteforge.etsy.wave_api as w, quoteforge.automation.emailer as em
    pushed = {"n": 0}
    monkeypatch.setattr(w, "create_money_transaction",
                        lambda *a, **k: pushed.__setitem__("n", pushed["n"] + 1)
                        or {"ok": True, "id": "T", "errors": []})
    monkeypatch.setattr(em, "_send_email", lambda *a, **k: {"status": "skipped"})
    from quoteforge import admin
    admin.main(["wave-sync", "month", "--auto"])      # flag OFF -> review only
    assert pushed["n"] == 0
    monkeypatch.setattr("quoteforge.config.WAVE_AUTO_SYNC", True)
    admin.main(["wave-sync", "month", "--auto"])      # flag ON -> auto push
    assert pushed["n"] >= 1


def test_monthly_wave_review_job_registered():
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    job = next((j for j in SCHEDULED_JOBS if j.name == "QuoteForge Wave Books Review"),
               None)
    assert job and job.admin_args == "wave-sync month email"
    assert "--live" not in job.admin_args        # the scheduled job can never push
