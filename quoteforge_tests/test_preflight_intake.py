"""Tests for artwork preflight, Etsy API client, polling, and tracking push."""
from unittest.mock import patch

from PIL import Image

from quoteforge.images.preflight import run_preflight
from quoteforge.automation import etsy_api, etsy_poller
from quoteforge import admin


def _img(path, size, mode="RGB", fmt="PNG"):
    Image.new(mode, size, (40, 60, 90)).save(path, fmt)
    return path


# ── Artwork preflight ────────────────────────────────────────────

def test_preflight_passes_correct_11x14(tmp_path):
    art = _img(tmp_path / "ok.png", (3300, 4200))  # 11x14 @ 300 DPI
    r = run_preflight(art, "11x14 in")
    assert r["ok"] is True
    assert all(c["ok"] for c in r["checks"])


def test_preflight_blocks_low_resolution(tmp_path):
    art = _img(tmp_path / "small.png", (600, 800))  # way under spec
    r = run_preflight(art, "11x14 in")
    assert r["ok"] is False
    assert any(c["name"] == "resolution" and not c["ok"] for c in r["checks"])


def test_preflight_blocks_wrong_aspect(tmp_path):
    # Square image for a portrait product -> aspect mismatch (crop risk).
    art = _img(tmp_path / "sq.png", (3300, 3300))
    r = run_preflight(art, "11x14 in")
    assert r["ok"] is False
    assert any(c["name"] == "aspect ratio" and not c["ok"] for c in r["checks"])


def test_preflight_blocks_missing_file(tmp_path):
    r = run_preflight(tmp_path / "nope.png", "11x14 in")
    assert r["ok"] is False


def test_preflight_blocks_bad_colour_mode(tmp_path):
    art = _img(tmp_path / "p.png", (3300, 4200), mode="P")  # palette
    r = run_preflight(art, "11x14 in")
    assert any(c["name"] == "colour mode" and not c["ok"] for c in r["checks"])


def test_pipeline_blocks_on_failed_preflight(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po

    # Force a tiny (failing) artwork file from the renderer.
    def _bad(*a, **k):
        out = k["output_path"]; out.parent.mkdir(parents=True, exist_ok=True)
        return _img(out, (300, 400))

    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "TEST_MODE", False), \
         patch.object(po, "PREFLIGHT_ENABLED", True), \
         patch.object(po, "GENERATE_ROOM_MOCKUP", False), \
         patch.object(po, "CUSTOMER_PROOF_APPROVAL", False), \
         patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", True), \
         patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
               return_value=None), \
         patch("quoteforge.images.local_renderer.render_local_poster",
               side_effect=_bad):
        db.init_db()
        po.run_full_pipeline({"order_id": "PF", "recipient_name": "Emma",
                              "occasion": "Graduation", "sender_name": "Mom",
                              "relationship": "Daughter",
                              "product_size": "11x14 in"}, skip_proof=True)
        order = db.get_order("PF")
        pending = db.get_pending_approvals()
    assert order["status"] == "preflight_failed"
    assert len(pending) == 1


# ── Etsy API client (TEST_MODE-safe) ─────────────────────────────

def test_etsy_receipts_mock_in_test_mode():
    with patch.object(etsy_api, "TEST_MODE", True):
        data = etsy_api.get_shop_receipts()
    assert data["mock"] is True


def test_create_receipt_shipment_mock():
    with patch.object(etsy_api, "TEST_MODE", True):
        r = etsy_api.create_receipt_shipment("R1", "1Z999", "ups")
    assert r["status"] == "mock_shipped"
    assert r["tracking_code"] == "1Z999"


def test_create_shipment_skips_without_tracking():
    r = etsy_api.create_receipt_shipment("R1", "")
    assert r["status"] == "skipped"


def test_receipt_to_payload_maps_fields():
    receipt = {"receipt_id": 555, "name": "Jane",
               "transactions": [{"variations": [
                   {"formatted_name": "Recipient Name", "formatted_value": "Emma"},
                   {"formatted_name": "Occasion", "formatted_value": "Graduation"}]}],
               "grandtotal": {"amount": 36.99}}
    p = etsy_api.receipt_to_order_payload(receipt)
    assert p["etsy_order_id"] == "555"
    assert p["recipient_name"] == "Emma"
    assert p["occasion"] == "Graduation"


# ── Poller ───────────────────────────────────────────────────────

def test_poll_once_imports_new_orders(tmp_path):
    import quoteforge.db.database as db
    receipt = {"receipt_id": 777, "name": "Jane",
               "transactions": [{"variations": [
                   {"formatted_name": "Recipient Name", "formatted_value": "Sam"},
                   {"formatted_name": "Occasion", "formatted_value": "Wedding"}]}]}
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.etsy_api.get_shop_receipts",
               return_value={"results": [receipt]}), \
         patch("quoteforge.automation.webhook_server.process_webhook_payload") as proc:
        db.init_db()
        res = etsy_poller.poll_once()
    assert "777" in res["imported"]
    proc.assert_called_once()


def test_poll_once_mock_noop():
    with patch("quoteforge.automation.etsy_api.get_shop_receipts",
               return_value={"mock": True, "results": []}):
        res = etsy_poller.poll_once()
    assert res["mock"] is True
    assert res["imported"] == []


# ── Gelato callback → Etsy tracking push ─────────────────────────

def test_gelato_callback_pushes_tracking_to_etsy(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation.webhook_server import process_gelato_callback
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               return_value={"status": "mock_shipped"}) as push:
        db.init_db()
        db.create_order({"order_id": "T9", "etsy_order_id": "R9",
                         "recipient_name": "X", "occasion": "Y"})
        res = process_gelato_callback({"orderReferenceId": "T9",
                                       "status": "shipped",
                                       "trackingCode": "1Z42"})
    assert res["etsy_tracking_push"]["status"] == "mock_shipped"
    push.assert_called_once()


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_preflight_art(tmp_path, capsys):
    art = _img(tmp_path / "ok.png", (3300, 4200))
    rc = admin.main(["preflight-art", str(art), "11x14 in"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PREFLIGHT" in out


def test_cli_poll_etsy_mock(capsys):
    with patch("quoteforge.automation.etsy_api.get_shop_receipts",
               return_value={"mock": True, "results": []}):
        rc = admin.main(["poll-etsy"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "mock" in out.lower()
