"""Tests for pre-launch marketing: Pinterest, email capture, subscribers, analytics."""
from pathlib import Path

from PIL import Image

from quoteforge.marketing import pinterest, email_capture, pinterest_publisher
from quoteforge.etsy.listing_preview import _analytics_snippet, build_shop_home


def _seed_kit(tmp_path):
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    for l in LAUNCH_PACK_20[:2]:
        g = tmp_path / f"{l.n:02d}_x" / "gallery"
        g.mkdir(parents=True)
        for name in ("1_hero.png", "2_close.png", "3_gift.png"):
            Image.new("RGB", (600, 800), (15, 61, 46)).save(g / name)
    return tmp_path


# ── Pinterest ────────────────────────────────────────────────────

def test_make_pin_is_2x3(tmp_path):
    src = tmp_path / "art.png"
    Image.new("RGB", (800, 800), (20, 60, 40)).save(src)
    out = pinterest.make_pin_image(src, tmp_path / "pin.png", "Hello", "Joffiels")
    assert out.exists()
    w, h = Image.open(out).size
    assert (w, h) == (pinterest.PIN_W, pinterest.PIN_H)   # 1000x1500


def test_build_pin_pack(tmp_path):
    _seed_kit(tmp_path)
    out_dir = tmp_path / "out"
    pins = pinterest.build_pin_pack(numbers=None, kit_dir=tmp_path, out_dir=out_dir)
    assert len(pins) >= 2 * len(pinterest.PIN_VARIANTS)   # several per product
    assert (out_dir / "pins.csv").exists()
    # each product pin has a title within Pinterest's 100-char limit
    assert all(len(p.title) <= 100 for p in pins)
    assert any(p.board == "Gift Guides" for p in pins)    # themed pins included


def test_pin_pack_empty_without_kit(tmp_path):
    assert pinterest.build_pin_pack(kit_dir=tmp_path, out_dir=tmp_path / "o") == []


# ── Email capture ────────────────────────────────────────────────

def test_capture_kit_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.SIGNUP_URL", "https://x.co/join", raising=False)
    r = email_capture.build_capture_kit(out_dir=tmp_path)
    for f in r["files"]:
        assert (tmp_path / f).exists()
    assert "https://x.co/join" in (tmp_path / "shop_announcement.txt").read_text(encoding="utf-8")


def test_qr_graceful_without_lib(tmp_path):
    # Whether or not qrcode is installed, this must not raise and must report.
    path, status = email_capture.make_qr("https://x.co/join", tmp_path / "qr.png")
    assert isinstance(status, str) and status


def test_signup_snippet_has_form():
    h = email_capture.signup_html_snippet("https://x.co/a")
    assert "<form" in h and "https://x.co/a" in h and 'type="email"' in h


# ── Subscribers DB ───────────────────────────────────────────────

def test_subscriber_add_and_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    assert db.add_subscriber("Fan@Example.com") is True
    assert db.add_subscriber("fan@example.com") is False   # dedupe (case-insensitive)
    assert db.add_subscriber("not-an-email") is False
    assert db.subscriber_count() == 1


# ── Pinterest auto-publish (dry-run safe) ────────────────────────

def test_publish_pins_dry_run_does_not_post(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.PINTEREST_ACCESS_TOKEN", "tok", raising=False)
    monkeypatch.setattr("quoteforge.config.PINTEREST_BOARD_ID", "b1", raising=False)
    monkeypatch.setattr("quoteforge.config.PINTEREST_AUTOPILOT", True, raising=False)
    _seed_kit(tmp_path)
    r = pinterest_publisher.publish_pins(kit_dir=tmp_path, out_dir=tmp_path / "p",
                                         live=False)
    assert r["generated"] > 0 and r["posted"] == 0 and r["live"] is False


def test_publish_pins_no_post_when_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.PINTEREST_ACCESS_TOKEN", "", raising=False)
    monkeypatch.setattr("quoteforge.config.PINTEREST_BOARD_ID", "", raising=False)
    monkeypatch.setattr("quoteforge.config.PINTEREST_AUTOPILOT", False, raising=False)
    _seed_kit(tmp_path)
    r = pinterest_publisher.publish_pins(kit_dir=tmp_path, out_dir=tmp_path / "p",
                                         live=True)
    assert r["configured"] is False and r["posted"] == 0 and r["live"] is False


# ── Auto-enroll buyer emails on order ────────────────────────────

def test_order_auto_enrolls_subscriber(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    from quoteforge.automation import webhook_server
    # Make the pipeline a no-op so we isolate the enrollment side-effect.
    monkeypatch.setattr(webhook_server, "_run_one",
                        lambda payload, oid: {"status": "duplicate"})
    webhook_server.process_webhook_payload(
        {"order_id": "X1", "customer_email": "Buyer@Shop.com"})
    assert db.subscriber_count() == 1
    assert db.get_subscribers()[0]["source"] == "etsy"


# ── Admin command registration ───────────────────────────────────

def test_new_commands_registered():
    from quoteforge import admin
    for c in ("pinterest", "pinterest-publish", "rebuild-site",
              "email-capture", "subscribers"):
        assert c in admin.COMMANDS


# ── Analytics injection ──────────────────────────────────────────

def test_analytics_empty_by_default(monkeypatch):
    monkeypatch.setattr("quoteforge.config.GA_MEASUREMENT_ID", "", raising=False)
    monkeypatch.setattr("quoteforge.config.CLARITY_PROJECT_ID", "", raising=False)
    assert _analytics_snippet() == ""


def test_analytics_injected_when_set(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.GA_MEASUREMENT_ID", "G-TEST123", raising=False)
    monkeypatch.setattr("quoteforge.config.CLARITY_PROJECT_ID", "abc123", raising=False)
    snippet = _analytics_snippet()
    assert "G-TEST123" in snippet and "clarity" in snippet
    _seed_kit(tmp_path)
    out = build_shop_home(kit_dir=tmp_path, out_path=tmp_path / "h.html")
    assert "G-TEST123" in out.read_text(encoding="utf-8")
