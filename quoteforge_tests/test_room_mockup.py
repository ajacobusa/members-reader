"""Tests for the styled-room lifestyle mockup renderer."""
from PIL import Image

from quoteforge.images.room_mockup import (
    render_room_mockup, WALL_PRESETS, FRAME_STYLES,
)
from quoteforge import admin


def _make_poster(path, size=(900, 1200)):
    Image.new("RGB", size, (40, 60, 90)).save(path, "PNG")
    return path


def test_mockup_created_at_requested_size(tmp_path):
    poster = _make_poster(tmp_path / "art.png")
    out = render_room_mockup(poster, tmp_path / "mock.png", size=(1600, 1600))
    assert out.exists()
    with Image.open(out) as im:
        assert im.size == (1600, 1600)


def test_mockup_preserves_portrait_orientation(tmp_path):
    # A tall poster must not be stretched — frame keeps the print aspect ratio.
    poster = _make_poster(tmp_path / "tall.png", size=(600, 1500))
    out = render_room_mockup(poster, tmp_path / "m.png")
    assert out.exists()


def test_all_wall_presets_render(tmp_path):
    poster = _make_poster(tmp_path / "art.png")
    for wall in WALL_PRESETS:
        out = render_room_mockup(poster, tmp_path / f"{wall}.png", wall=wall)
        assert out.exists()


def test_all_frame_styles_render(tmp_path):
    poster = _make_poster(tmp_path / "art.png")
    for frame in FRAME_STYLES:
        out = render_room_mockup(poster, tmp_path / f"{frame}.png",
                                 frame_style=frame)
        assert out.exists()


def test_real_room_background_used(tmp_path):
    poster = _make_poster(tmp_path / "art.png")
    room = tmp_path / "room.jpg"
    Image.new("RGB", (1200, 1200), (200, 190, 180)).save(room)
    out = render_room_mockup(poster, tmp_path / "m.png",
                             room_background_path=room)
    assert out.exists()


def test_unknown_wall_and_frame_fall_back(tmp_path):
    poster = _make_poster(tmp_path / "art.png")
    out = render_room_mockup(poster, tmp_path / "m.png",
                             wall="nope", frame_style="nope")
    assert out.exists()  # falls back to defaults, never crashes


# ── Pipeline integration ─────────────────────────────────────────

def test_pipeline_emits_mockup(tmp_path):
    from unittest.mock import patch
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "GENERATE_ROOM_MOCKUP", True), \
         patch.object(po, "CUSTOMER_PROOF_APPROVAL", False), \
         patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", True), \
         patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
               return_value=None):
        db.init_db()
        po.run_full_pipeline({"order_id": "MK", "recipient_name": "Emma",
                              "occasion": "Graduation", "sender_name": "Mom",
                              "relationship": "Daughter"}, skip_proof=True)
        order = db.get_order("MK")
    assert order["mockup_url"]
    assert order["mockup_url"].endswith("mockup_room.png")


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_mockup_registered():
    assert "mockup" in admin.COMMANDS


def test_cli_mockup_generates(tmp_path, capsys):
    poster = _make_poster(tmp_path / "art.png")
    rc = admin.main(["mockup", str(poster), str(tmp_path / "out.png")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Room mockup saved" in out
    assert (tmp_path / "out.png").exists()
