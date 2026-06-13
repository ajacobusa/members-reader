"""Tests for cost-reduction changes: free local Pillow renderer + Haiku model."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from quoteforge.images.local_renderer import (
    render_local_poster, _wrap_to_width, _cover_resize, _load_font,
)


def _fake_bg_response(w=1200, h=1600):
    """A real in-memory PNG so the renderer's Image.open works."""
    img = Image.new("RGB", (w, h), (80, 120, 160))
    buf = BytesIO()
    img.save(buf, "PNG")
    resp = MagicMock()
    resp.content = buf.getvalue()
    resp.raise_for_status = lambda: None
    return resp


# ── Local renderer ───────────────────────────────────────────────

def test_render_with_solid_background(tmp_path):
    out = render_local_poster(
        quote="Rise above the storm.",
        output_path=tmp_path / "poster.png",
        size=(600, 800),  # small for fast test
    )
    assert out.exists()
    img = Image.open(out)
    assert img.size == (600, 800)
    assert img.format == "PNG"


def test_render_with_downloaded_background(tmp_path):
    with patch("quoteforge.images.local_renderer.requests.get",
               return_value=_fake_bg_response()):
        out = render_local_poster(
            quote="The mountains are calling.",
            output_path=tmp_path / "poster.png",
            background_url="https://images.unsplash.com/photo-x",
            size=(600, 800),
        )
    assert out.exists()
    assert Image.open(out).size == (600, 800)


def test_render_exports_300_dpi(tmp_path):
    out = render_local_poster(
        quote="Test", output_path=tmp_path / "p.png", size=(600, 800),
    )
    img = Image.open(out)
    dpi = img.info.get("dpi")
    assert dpi is not None
    assert round(dpi[0]) == 300 and round(dpi[1]) == 300


def test_render_long_quote_does_not_overflow(tmp_path):
    long_quote = ("This is a very long inspirational quote that should wrap "
                  "across multiple lines and shrink to fit within the poster "
                  "without overflowing the canvas boundaries at all.")
    out = render_local_poster(
        quote=long_quote, output_path=tmp_path / "p.png", size=(600, 800),
    )
    assert out.exists()  # renders without error


def test_render_with_attribution(tmp_path):
    out = render_local_poster(
        quote="You are loved.", output_path=tmp_path / "p.png",
        size=(600, 800), attribution="— With love, Mom",
    )
    assert out.exists()


def test_wrap_to_width_splits_text():
    img = Image.new("RGB", (100, 100))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    font = _load_font(20)
    lines = _wrap_to_width(draw, "one two three four five six", font, max_width=60)
    assert len(lines) >= 2  # wrapped into multiple lines


def test_cover_resize_fills_target():
    img = Image.new("RGB", (1000, 500))
    resized = _cover_resize(img, (400, 400))
    assert resized.size == (400, 400)


# ── Model cost config ────────────────────────────────────────────

def test_default_model_is_haiku():
    import quoteforge.config as cfg
    # Default ships as Haiku for cost; overridable via CLAUDE_MODEL env
    assert "haiku" in cfg.CLAUDE_MODEL.lower()


def test_renderer_defaults_to_local():
    import quoteforge.config as cfg
    assert cfg.RENDERER == "local"


# ── Pipeline uses local renderer (no Bannerbear needed) ──────────

def test_pipeline_renders_locally_without_bannerbear(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "OUTPUT_DIR", tmp_path), \
         patch.object(po, "TEST_MODE", False), \
         patch.object(po, "RENDERER", "local"), \
         patch.object(po, "BANNERBEAR_TEMPLATE_UID", "YOUR_BANNERBEAR_TEMPLATE_UID"), \
         patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
               return_value=None), \
         patch("quoteforge.quotes.generator.TEST_MODE", True):  # mock quote
        db.init_db()
        result = po.run_full_pipeline(
            {"order_id": "LOCAL-1", "recipient_name": "Emma", "occasion": "Graduation",
             "sender_name": "Mom", "relationship": "To My Daughter"},
            skip_proof=True, gelato_product_uid="poster_18x24_uid",
            recipient_address={"name": "Emma", "address": "1 Main St",
                               "city": "Atlanta", "state": "GA",
                               "postCode": "30301", "country": "US"},
        )
    png = tmp_path / "pipeline" / "LOCAL-1" / "artwork.png"
    assert png.exists()  # real poster rendered with Pillow, no Bannerbear
    assert result["status"] == "shipped"
