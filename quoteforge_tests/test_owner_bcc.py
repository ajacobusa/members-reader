"""The owner (ajacobusa@gmail.com) is BCC'd on every outgoing email."""
from unittest.mock import patch, MagicMock

import quoteforge.automation.emailer as emailer


def _capture_sendmail():
    captured = {}

    class FakeServer:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def sendmail(self, frm, to_list, body):
            captured["from"] = frm
            captured["envelope"] = to_list
    return captured, FakeServer


def test_owner_bcc_on_customer_email():
    captured, FakeServer = _capture_sendmail()
    with patch.object(emailer, "GMAIL_ADDRESS", "shop@gmail.com"), \
         patch.object(emailer, "GMAIL_APP_PASSWORD", "pw"), \
         patch.object(emailer, "REPORT_RECIPIENT", "ajacobusa@gmail.com"), \
         patch("smtplib.SMTP_SSL", return_value=FakeServer()):
        out = emailer._send_email("hi", "<p>body</p>", to="buyer@x.com")
    # buyer is the visible recipient; owner is BCC'd on the envelope
    assert "buyer@x.com" in captured["envelope"]
    assert "ajacobusa@gmail.com" in captured["envelope"]
    assert out["bcc"] == "ajacobusa@gmail.com"


def test_no_duplicate_when_owner_is_recipient():
    captured, FakeServer = _capture_sendmail()
    with patch.object(emailer, "GMAIL_ADDRESS", "shop@gmail.com"), \
         patch.object(emailer, "GMAIL_APP_PASSWORD", "pw"), \
         patch.object(emailer, "REPORT_RECIPIENT", "ajacobusa@gmail.com"), \
         patch("smtplib.SMTP_SSL", return_value=FakeServer()):
        emailer._send_email("report", "<p>x</p>")   # to owner by default
    # owner appears exactly once
    assert captured["envelope"].count("ajacobusa@gmail.com") == 1


def test_skips_cleanly_without_creds():
    with patch.object(emailer, "GMAIL_ADDRESS", ""), \
         patch.object(emailer, "GMAIL_APP_PASSWORD", ""):
        out = emailer._send_email("s", "b", to="c@x.com")
    assert out["status"] == "skipped"
