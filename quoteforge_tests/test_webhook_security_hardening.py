"""REGRESSION: webhook / endpoint security hardening (v2 audit).

The Etsy /order webhook and Gelato /gelato callback are the live order+status
intake, so signature verification must FAIL CLOSED in production; /upload must not
let one customer mutate another's order; /backup must not be an open trigger.
"""
import io

import pytest

from quoteforge.automation import webhook_security as ws


def _real_jpg() -> io.BytesIO:
    """A genuinely decodable JPEG (the /upload decode-integrity guard rejects bytes
    that aren't a real image, so these IDOR tests must send a true image)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (20, 80, 60)).save(buf, "JPEG")
    buf.seek(0)
    return buf


# ── signature verification fails CLOSED in live, dev-parity in TEST_MODE ──────
def test_verify_fails_closed_in_live_without_secret(monkeypatch):
    # REGRESSION: _verify returned True when no secret was set - a blank secret in
    # production silently accepted unsigned/spoofed webhooks.
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)   # live
    assert ws._verify(b"body", "anything", "") is False         # reject
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True)    # dev
    assert ws._verify(b"body", "anything", "") is True          # skip (parity)


def test_verify_enforces_a_configured_secret(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    good = ws.compute_signature(b"body", "sek")
    assert ws._verify(b"body", good, "sek") is True
    assert ws._verify(b"body", "wrong", "sek") is False
    assert ws._verify(b"body", "", "sek") is False              # missing sig


# ── go-live hard-fails until the Gelato callback secret is configured ─────────
def test_gelato_webhook_secret_is_required_for_go_live():
    # REGRESSION: GELATO_WEBHOOK_SECRET was not gated, so a fail-open Gelato
    # callback could reach production. Go-live preflight must require it.
    from quoteforge.preflight import REQUIRED_LIVE_KEYS
    assert "GELATO_WEBHOOK_SECRET" in REQUIRED_LIVE_KEYS


# ── /upload may not mutate an order that isn't the submitter's (IDOR) ─────────
def test_upload_cannot_mutate_another_users_order(monkeypatch, tmp_path):
    # REGRESSION: order_id was an attacker-controlled form field with no ownership
    # check, so anyone could overwrite any order's print file / artwork / status.
    flask = pytest.importorskip("flask")  # noqa: F841
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    db.create_order({"order_id": "OID1", "customer_email": "owner@x.com",
                     "recipient_name": "Owner", "occasion": "Birthday"})
    # Stub the heavy upload internals so the route reaches the ownership guard.
    monkeypatch.setattr("quoteforge.customers.save_upload",
                        lambda *a, **k: str(tmp_path / "saved.jpg"))
    monkeypatch.setattr("quoteforge.automation.print_quality.assess_photo",
                        lambda *a, **k: {"decision": "approve", "reasons": []})
    monkeypatch.setattr("quoteforge.automation.print_quality.ai_focal_point",
                        lambda *a, **k: {})
    monkeypatch.setattr("quoteforge.automation.file_host.publish_print_file",
                        lambda *a, **k: {"url": "http://x/y.jpg", "public": True,
                                         "host": "local"})
    from quoteforge.automation.webhook_server import app
    client = app.test_client()
    resp = client.post("/upload", content_type="multipart/form-data", data={
        "email": "attacker@x.com", "order_id": "OID1",
        "file": (_real_jpg(), "evil.jpg")})
    assert resp.status_code == 200            # upload itself still processes
    o = db.get_order("OID1")
    assert not o.get("print_file")            # but the victim's order is UNTOUCHED
    assert o.get("status") != "hold_photo"


def test_upload_does_mutate_the_owners_order(monkeypatch, tmp_path):
    # The legitimate path still works: the owner's own upload attaches to the order.
    pytest.importorskip("flask")
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    db.create_order({"order_id": "OID2", "customer_email": "owner@x.com",
                     "recipient_name": "Owner", "occasion": "Birthday"})
    monkeypatch.setattr("quoteforge.customers.save_upload",
                        lambda *a, **k: str(tmp_path / "saved.jpg"))
    monkeypatch.setattr("quoteforge.automation.print_quality.assess_photo",
                        lambda *a, **k: {"decision": "approve", "reasons": []})
    monkeypatch.setattr("quoteforge.automation.print_quality.ai_focal_point",
                        lambda *a, **k: {})
    monkeypatch.setattr("quoteforge.automation.file_host.publish_print_file",
                        lambda *a, **k: {"url": "http://x/y.jpg", "public": True,
                                         "host": "local"})
    from quoteforge.automation.webhook_server import app
    client = app.test_client()
    resp = client.post("/upload", content_type="multipart/form-data", data={
        "email": "owner@x.com", "order_id": "OID2",
        "file": (_real_jpg(), "ok.jpg")})
    assert resp.status_code == 200
    assert db.get_order("OID2").get("artwork_url") == "http://x/y.jpg"


# ── /backup is signature-gated (not an open DB-snapshot trigger) ─────────────
def test_backup_endpoint_rejects_unsigned_when_secret_set(monkeypatch):
    # REGRESSION: /backup was unauthenticated; anyone could trigger DB snapshots.
    pytest.importorskip("flask")
    monkeypatch.setattr(
        "quoteforge.automation.webhook_security.ETSY_WEBHOOK_SECRET", "sek")
    from quoteforge.automation.webhook_server import app
    resp = app.test_client().post("/backup", data=b"{}")
    assert resp.status_code == 401            # no signature + secret set -> rejected
