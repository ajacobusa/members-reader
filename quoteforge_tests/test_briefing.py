"""Tests for the morning briefing + photo-resume."""
from datetime import datetime
from unittest.mock import patch

from PIL import Image

from quoteforge.automation.briefing import morning_briefing, format_briefing_text
from quoteforge import admin


def test_briefing_aggregates(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "B1", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        db.update_order("B1", status="needs_better_photo")
        b = morning_briefing(datetime(2026, 6, 5))
    assert b["orders_total"] == 1
    assert b["photo_holds"] == 1
    # photo hold should be surfaced as an action
    assert any("photo" in a.lower() for a in b["actions"])


def test_briefing_text_renders(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        text = format_briefing_text(morning_briefing())
    assert "MORNING BRIEFING" in text and "ACTION NEEDED" in text


def test_briefing_degrades_gracefully(tmp_path):
    # Even if an agent errors, the briefing still returns a dict.
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.etsy.retention.retention_digest",
               side_effect=RuntimeError("boom")):
        db.init_db()
        b = morning_briefing()
    assert "actions" in b and b["repeat_gift"] == 0


def test_cli_briefing(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.healthcheck.OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["briefing"])
    out = capsys.readouterr().out
    assert rc == 0 and "MORNING BRIEFING" in out


# ── Photo resume ─────────────────────────────────────────────────

def test_fix_photo_resumes_held_order(tmp_path, capsys):
    import quoteforge.db.database as db
    good = tmp_path / "good.jpg"
    Image.new("RGB", (3600, 4800), (90, 90, 90)).save(good)
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "FX1", "recipient_name": "Buddy",
                         "occasion": "Pet Memorial", "product_size": "18x24 in"})
        db.update_order("FX1", status="needs_better_photo",
                        generated_quote="Best dog ever.")
        rc = admin.main(["fix-photo", "FX1", str(good)])
        order = db.get_order("FX1")
    out = capsys.readouterr().out
    assert rc == 0 and "resumed" in out
    assert order["status"] != "needs_better_photo"   # moved forward


def test_fix_photo_rejects_still_low_res(tmp_path, capsys):
    import quoteforge.db.database as db
    bad = tmp_path / "bad.jpg"
    Image.new("RGB", (500, 700), (90, 90, 90)).save(bad)
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "FX2", "recipient_name": "X",
                         "occasion": "Y", "product_size": "18x24 in"})
        db.update_order("FX2", status="needs_better_photo")
        rc = admin.main(["fix-photo", "FX2", str(bad)])
    out = capsys.readouterr().out
    assert rc == 1 and "still too low" in out.lower()
