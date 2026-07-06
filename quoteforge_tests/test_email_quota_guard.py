"""Email quota guard - a customer's transactional email is never dropped because the shared
Gmail send cap was exhausted. Central at emailer._send_email:
  * TEST_MODE (unless force) sends NO real email - tests/dev/CI never burn the quota.
  * CUSTOMER (critical) email always sends, never owner-BCC'd (halves its quota cost).
  * NON-critical email (reports/marketing) defers once the daily budget is reached.
All SMTP is mocked - no real send.
"""
import pytest

from quoteforge.automation import emailer as em


@pytest.fixture
def mock_smtp(tmp_path, monkeypatch):
    # TEST_MODE + budget are read live from config inside _send_email; the credential/
    # recipient names are imported into the emailer module at import, so patch em.* for those.
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr(em, "GMAIL_ADDRESS", "send@x.com")
    monkeypatch.setattr(em, "GMAIL_APP_PASSWORD", "pw")
    monkeypatch.setattr(em, "REPORT_RECIPIENT", "owner@x.com")
    sent = []

    class _S:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def login(self, *a): pass
        def sendmail(self, frm, env, msg): sent.append(list(env))
    monkeypatch.setattr(em.smtplib, "SMTP_SSL", lambda *a, **k: _S())
    return sent


def test_test_mode_sends_no_real_email(tmp_path, monkeypatch):
    # THE fix: in TEST_MODE nothing is sent (so tests/dev/CI never burn the shared quota).
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)
    monkeypatch.setattr("quoteforge.config.GMAIL_ADDRESS", "send@x.com")
    monkeypatch.setattr("quoteforge.config.GMAIL_APP_PASSWORD", "pw")
    assert em._send_email("s", "b", to="x@y.com")["status"] == "skipped"


def test_no_creds_skips(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr(em, "GMAIL_ADDRESS", "")            # emailer's imported copy
    assert em._send_email("s", "b", to="x@y.com", force=True)["status"] == "skipped"


def test_customer_email_sends_without_owner_bcc(mock_smtp):
    r = em._send_email("order shipped", "b", to="buyer@x.com",
                       critical=True, bcc_owner=False)
    assert r["status"] == "sent" and r["bcc"] == ""
    assert mock_smtp[-1] == ["buyer@x.com"]              # buyer only, no owner copy


def test_owner_report_bcc_included(mock_smtp):
    r = em._send_email("daily report", "b", to="somebody@x.com")   # default bcc_owner=True
    assert "owner@x.com" in mock_smtp[-1]                # owner BCC'd on reports


def test_non_critical_defers_over_budget_but_customer_always_sends(mock_smtp, monkeypatch):
    monkeypatch.setattr("quoteforge.config.EMAIL_DAILY_BUDGET", 1)
    assert em._send_email("first", "b", to="a@x.com", critical=True, bcc_owner=False)["status"] == "sent"
    # budget now reached -> a NON-critical email defers...
    assert em._send_email("report", "b", to="b@x.com")["status"] == "deferred"
    # ...but a CUSTOMER (critical) email still goes through - never dropped.
    assert em._send_email("shipped", "b", to="c@x.com", critical=True, bcc_owner=False)["status"] == "sent"


def test_send_counter_increments(mock_smtp):
    assert em.sends_today() == 0
    em._send_email("s", "b", to="a@x.com", critical=True, bcc_owner=False)
    assert em.sends_today() == 1


def test_customer_paths_marked_critical():
    # REGRESSION: the buyer-facing send sites must pass critical=True so a customer email is
    # never deferred by the budget.
    import inspect
    from quoteforge.automation import customer_notify, pipeline_orchestrator, customization_recovery
    for mod in (customer_notify, pipeline_orchestrator, customization_recovery):
        src = inspect.getsource(mod)
        assert "critical=True" in src, f"{mod.__name__} customer send not marked critical"
