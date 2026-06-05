"""Tests for buyer-supplied custom text (verbatim) and custom image."""
from unittest.mock import patch

from PIL import Image


def _patches(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    return [
        patch.object(db, "DB_PATH", tmp_path / "t.db"),
        patch.object(db, "OUTPUT_DIR", tmp_path),
        patch.object(po, "OUTPUT_DIR", tmp_path),
        patch.object(po, "RENDERER", "local"),
        patch.object(po, "TEST_MODE", False),
        patch.object(po, "PREFLIGHT_ENABLED", False),
        patch.object(po, "GENERATE_ROOM_MOCKUP", False),
        patch.object(po, "CUSTOMER_PROOF_APPROVAL", False),
        patch.object(po, "PIPELINE_AUTO_APPROVE_PROOF", True),
        patch("quoteforge.automation.pipeline_orchestrator.fetch_background_url",
              return_value=None),
    ]


def test_verbatim_custom_text_skips_ai(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    exact = "Forever in our hearts, Grandpa Joe. 1940-2026."
    with patch("quoteforge.quotes.generator.generate_personal_message") as gen:
        gen.side_effect = AssertionError("AI must NOT be called for custom text")
        for p in _patches(tmp_path):
            p.start()
        try:
            db.init_db()
            po.run_full_pipeline({
                "order_id": "CT1", "recipient_name": "Grandpa",
                "occasion": "Memorial", "custom_text": exact}, skip_proof=True)
            order = db.get_order("CT1")
        finally:
            for p in reversed(_patches(tmp_path)):
                pass
            patch.stopall()
    assert order["generated_quote"] == exact   # used verbatim, no AI


def test_custom_image_used_as_background(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import pipeline_orchestrator as po
    # A buyer-supplied photo on disk.
    photo = tmp_path / "pet.png"
    Image.new("RGB", (3600, 4800), (200, 120, 80)).save(photo)  # print-quality
    captured = {}

    def _fake_render(**kwargs):
        captured.update(kwargs)
        out = kwargs["output_path"]; out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", kwargs.get("size", (5400, 7200)), (10, 10, 10)).save(out)
        return out

    for p in _patches(tmp_path):
        p.start()
    try:
        with patch("quoteforge.images.local_renderer.render_local_poster",
                   side_effect=_fake_render):
            db.init_db()
            po.run_full_pipeline({
                "order_id": "CI1", "recipient_name": "Buddy",
                "occasion": "Pet Memorial", "custom_text": "Best dog ever.",
                "custom_image": str(photo)}, skip_proof=True)
    finally:
        patch.stopall()
    # The buyer's photo was passed as the background_path.
    assert str(captured.get("background_path")) == str(photo)


def test_webhook_maps_custom_fields():
    from quoteforge.automation.webhook_server import _build_order_data
    od = _build_order_data(
        {"recipient_name": "X", "occasion": "Y",
         "custom_quote": "my exact words", "custom_photo": "http://img/x.jpg"},
        "E1")
    assert od["custom_text"] == "my exact words"
    assert od["custom_image"] == "http://img/x.jpg"
