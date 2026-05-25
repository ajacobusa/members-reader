import pytest
from stock_dashboard.notifier import build_html_email, send_email
from stock_dashboard.db.database import PickRecord
from stock_dashboard.engine.config_loader import load_config


def _picks():
    return [
        PickRecord(
            date="2026-05-25", ticker="NVDA", company="NVIDIA Corp",
            price=892.0, composite_score=94.0, technical_score=88.0,
            fundamental_score=91.0, catalyst_score=95.0, pattern_score=0.0,
            catalysts=[{"type": "earnings_beat", "label": "Earnings Beat +18%"}],
            narrative="Earnings Beat +18% · EPS growth 43% YoY",
            signals={"rsi": 62.0},
        ),
    ]


def test_build_html_contains_ticker(config_path):
    cfg = load_config(config_path)
    html = build_html_email(_picks(), market_favorable=True, cfg=cfg)
    assert "NVDA" in html


def test_build_html_contains_score(config_path):
    cfg = load_config(config_path)
    html = build_html_email(_picks(), market_favorable=True, cfg=cfg)
    assert "94" in html


def test_build_html_contains_narrative(config_path):
    cfg = load_config(config_path)
    html = build_html_email(_picks(), market_favorable=True, cfg=cfg)
    assert "Earnings Beat" in html


def test_build_html_market_unfavorable_banner(config_path):
    cfg = load_config(config_path)
    html = build_html_email([], market_favorable=False, cfg=cfg)
    assert "unfavorable" in html.lower()


def test_send_email_skips_when_disabled(config_path, mocker):
    cfg = load_config(config_path)  # email.enabled = false in fixture
    mock_smtp = mocker.patch("smtplib.SMTP")
    send_email("subject", "<p>body</p>", cfg)
    mock_smtp.assert_not_called()


def test_send_email_skips_when_no_app_password(config_path, mocker):
    cfg = load_config(config_path)
    cfg.email["enabled"] = True
    cfg.email["app_password"] = ""
    mock_smtp = mocker.patch("smtplib.SMTP")
    send_email("subject", "<p>body</p>", cfg)
    mock_smtp.assert_not_called()


def test_send_email_calls_smtp_when_configured(config_path, mocker):
    cfg = load_config(config_path)
    cfg.email["enabled"] = True
    cfg.email["app_password"] = "test-app-password"
    mock_smtp_class = mocker.patch("smtplib.SMTP")
    mock_server = mock_smtp_class.return_value.__enter__.return_value
    send_email("Test Subject", "<p>body</p>", cfg)
    mock_smtp_class.assert_called_once_with(cfg.email["smtp_host"], cfg.email["smtp_port"])
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with(cfg.email["sender"], "test-app-password")
