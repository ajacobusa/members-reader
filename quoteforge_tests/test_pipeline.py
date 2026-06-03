from unittest.mock import patch
from pathlib import Path
from quoteforge.pipeline import run_pipeline

def test_run_pipeline_returns_results(tmp_path):
    with patch("quoteforge.pipeline.generate_quotes", return_value=["Rise above the storm."]), \
         patch("quoteforge.pipeline.get_mood", return_value="powerful"), \
         patch("quoteforge.pipeline.get_unsplash_keyword", return_value="mountain peak"), \
         patch("quoteforge.pipeline.fetch_background_url", return_value="https://unsplash.com/photo"), \
         patch("quoteforge.pipeline.render_poster", return_value="https://cdn.bannerbear.com/img.png"), \
         patch("quoteforge.pipeline.download_png", return_value=tmp_path / "design.png"), \
         patch("quoteforge.pipeline.generate_listing", return_value={"title": "T", "tags": [], "description": "D"}):
        results = run_pipeline(
            category="Motivation & Mindset",
            subcategory="Growth mindset",
            count=1,
            template_uid="tmpl_abc",
            output_dir=tmp_path,
        )
    assert len(results) == 1
    assert "quote" in results[0]
    assert "png_path" in results[0]
    assert "listing" in results[0]

def test_run_pipeline_skips_failed_background(tmp_path):
    with patch("quoteforge.pipeline.generate_quotes", return_value=["Quote one.", "Quote two."]), \
         patch("quoteforge.pipeline.get_mood", return_value="serene"), \
         patch("quoteforge.pipeline.get_unsplash_keyword", return_value="nature"), \
         patch("quoteforge.pipeline.fetch_background_url", return_value=None), \
         patch("quoteforge.pipeline.render_poster") as mock_render, \
         patch("quoteforge.pipeline.download_png") as mock_dl, \
         patch("quoteforge.pipeline.generate_listing"):
        results = run_pipeline("Nature & Peace", "Mountain serenity", 2, "tmpl", tmp_path)
    assert results == []
    mock_render.assert_not_called()
    mock_dl.assert_not_called()

def test_run_pipeline_calls_on_progress(tmp_path):
    progress_calls = []
    def on_progress(current, total, quote):
        progress_calls.append((current, total, quote))

    with patch("quoteforge.pipeline.generate_quotes", return_value=["Rise above."]), \
         patch("quoteforge.pipeline.get_mood", return_value="powerful"), \
         patch("quoteforge.pipeline.get_unsplash_keyword", return_value="mountain"), \
         patch("quoteforge.pipeline.fetch_background_url", return_value="https://unsplash.com/photo"), \
         patch("quoteforge.pipeline.render_poster", return_value="https://cdn.bannerbear.com/img.png"), \
         patch("quoteforge.pipeline.download_png", return_value=tmp_path / "design.png"), \
         patch("quoteforge.pipeline.generate_listing", return_value={"title": "T", "tags": [], "description": "D"}):
        run_pipeline("Motivation & Mindset", "Resilience", 1, "tmpl", tmp_path, on_progress=on_progress)
    assert len(progress_calls) == 1
    assert progress_calls[0][1] == 1
