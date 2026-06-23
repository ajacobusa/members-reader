"""Shared AI design-assistant: deterministic photo review + placement (no network)."""

from quoteforge.ai.design_assistant import (
    photo_quality_review, placement_suggestion, ai_photo_review)


def test_high_res_photo_scores_great():
    r = photo_quality_review(4000, 3000, "wallart", "18x24")
    assert r["score"] >= 80 and r["verdict"] == "Great photo"
    assert r["mp"] == 12.0
    assert r["max_print_in"][0] > 20            # 4000/150 ~ 26.6 in


def test_low_res_photo_is_flagged():
    r = photo_quality_review(600, 400, "wallart", "18x24")
    assert r["score"] < 55
    assert any("Low resolution" in t for t in r["tips"])
    assert r["verdict"] == "Use a higher-quality photo"


def test_no_image_is_safe():
    r = photo_quality_review(0, 0, "mug", "11oz")
    assert r["score"] == 0 and r["verdict"] == "No image"


def test_crop_warning_for_tall_photo_on_wide_mug():
    # a tall portrait photo on the wide mug wrap warns about side cropping
    r = photo_quality_review(2000, 3500, "mug", "11oz")
    assert r["crop"]
    assert any("crop" in t.lower() for t in r["tips"])


def test_placement_landscape_photo_with_text_uses_banner():
    s = placement_suggestion(4000, 2000, 1, "wallart")
    assert s["layout"] == "banner"
    assert s["text_pos"]["y"] > 0.7             # caption sits below the wide photo


def test_placement_portrait_photo_with_text_uses_badge():
    s = placement_suggestion(2000, 3000, 2, "mug")
    assert s["layout"] == "badge"


def test_placement_no_photo_is_freeform_centered():
    s = placement_suggestion(0, 0, 1, "apparel")
    assert s["layout"] == "freeform" and s["text_pos"]["x"] == 0.5


def test_ai_photo_review_falls_back_to_deterministic_without_ai(tmp_path):
    # No real image / TEST_MODE -> deterministic review only, never raises.
    r = ai_photo_review(None, "wallart", "18x24", width=4000, height=3000)
    assert r["score"] >= 80
    assert r["ai_ok"] is True


def test_editor_wires_the_ai_assistant_for_all_products():
    # The shared editor (apparel/mug/calendar/branded/wall-art) exposes the AI Smart
    # review card + Auto-arrange, mirroring this module - so every product gets it.
    import pathlib
    from quoteforge.etsy import listing_preview as lp
    src = pathlib.Path(lp.__file__).read_text(encoding="utf-8")
    for marker in ("function _photoReview", "function renderPhotoReview",
                   "function autoArrange", "Smart photo review:",
                   "renderPhotoReview(msg,"):
        assert marker in src, f"AI assistant marker missing: {marker}"
