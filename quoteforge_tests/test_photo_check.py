"""Tests for the customer photo quality gate + auto-reply."""
from unittest.mock import patch

from PIL import Image

from quoteforge.images.photo_check import check_customer_photo, photo_request_message
from quoteforge import admin


def _photo(path, size):
    Image.new("RGB", size, (120, 90, 60)).save(path, "JPEG")
    return path


def test_high_res_photo_passes(tmp_path):
    p = _photo(tmp_path / "good.jpg", (3600, 4800))   # plenty for 18x24
    chk = check_customer_photo(p, "18x24 in")
    assert chk["ok"] is True
    assert chk["effective_dpi"] >= 120


def test_low_res_photo_fails(tmp_path):
    p = _photo(tmp_path / "bad.jpg", (600, 800))      # phone-screenshot small
    chk = check_customer_photo(p, "18x24 in")
    assert chk["ok"] is False
    assert chk["needs_resend"] is True
    assert "resolution" in chk["reason"]


def test_small_photo_ok_for_small_print(tmp_path):
    # The same 1200x1500 photo is fine for an 8x10 but not an 18x24.
    p = _photo(tmp_path / "m.jpg", (1200, 1500))
    assert check_customer_photo(p, "8x10 in")["ok"] is True
    assert check_customer_photo(p, "18x24 in")["ok"] is False


def test_missing_file(tmp_path):
    chk = check_customer_photo(tmp_path / "nope.jpg", "18x24 in")
    assert chk["ok"] is False and chk["needs_resend"] is True


def test_request_message_is_specific_and_polite(tmp_path):
    p = _photo(tmp_path / "bad.jpg", (600, 800))
    chk = check_customer_photo(p, "18x24 in")
    msg = photo_request_message(chk, "Jen", "Emma")
    assert "Jen" in msg and "Emma" in msg
    assert "600x800" in msg and "screenshot" in msg.lower()


# ── Pipeline integration: bad photo halts + stages auto-reply ────

def test_pipeline_halts_and_replies_on_bad_photo(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    bad = _photo(tmp_path / "low.jpg", (500, 700))
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "TEST_MODE", False), \
         patch.object(po, "GENERATE_ROOM_MOCKUP", False), \
         patch.object(po, "CUSTOMER_PROOF_APPROVAL", False), \
         patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", True), \
         patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
               return_value=None), \
         patch("quoteforge.automation.pipeline_orchestrator._auto_email_customer") as mail:
        db.init_db()
        po.run_full_pipeline({
            "order_id": "PH1", "recipient_name": "Buddy", "occasion": "Pet Memorial",
            "custom_text": "Best dog ever.", "custom_image": str(bad),
            "product_size": "18x24 in", "customer_email": "c@x.com"},
            skip_proof=True)
        order = db.get_order("PH1")
        msgs = db.get_customer_messages("PH1")
        pending = db.get_pending_approvals()
    assert order["status"] == "needs_better_photo"        # did NOT print
    assert any(m["message_type"] == "photo_request" for m in msgs)
    assert len(pending) == 1
    mail.assert_called_once()                              # auto-reply attempted


def test_pipeline_proceeds_on_good_photo(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    good = _photo(tmp_path / "hi.jpg", (3600, 4800))
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "TEST_MODE", False), \
         patch.object(po, "PREFLIGHT_ENABLED", False), \
         patch.object(po, "GENERATE_ROOM_MOCKUP", False), \
         patch.object(po, "CUSTOMER_PROOF_APPROVAL", False), \
         patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", True):
        db.init_db()
        po.run_full_pipeline({
            "order_id": "PH2", "recipient_name": "Buddy", "occasion": "Pet Memorial",
            "custom_text": "Best dog ever.", "custom_image": str(good),
            "product_size": "18x24 in"}, skip_proof=True)
        order = db.get_order("PH2")
    assert order["status"] != "needs_better_photo"


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_check_photo(tmp_path, capsys):
    p = _photo(tmp_path / "bad.jpg", (600, 800))
    rc = admin.main(["check-photo", str(p), "18x24 in"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "TOO LOW" in out and "Auto-reply" in out
