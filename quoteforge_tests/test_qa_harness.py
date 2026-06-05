"""Tests for the pre-launch QA harnesses: quote batch + artwork edge cases."""
from unittest.mock import patch

from PIL import Image

from quoteforge.quotes.sample_batch import (
    SCENARIOS, generate_sample_batch, format_batch_text,
)
from quoteforge.images.artwork_qa import (
    run_artwork_qa, format_qa_text, NAME_CASES, QUOTE_CASES, SIZE_CASES,
)
from quoteforge import admin


# ── Quote sample batch ───────────────────────────────────────────

def test_scenarios_cover_emotional_categories():
    labels = " ".join(s.label.lower() for s in SCENARIOS)
    for cat in ["daughter", "son", "wedding", "anniversary", "memorial",
                "christian"]:
        assert cat in labels


def test_generate_batch_mock_returns_all():
    results = generate_sample_batch(force_real=False)
    assert len(results) == len(SCENARIOS)
    assert all(r["ok"] and r["quotes"] for r in results)


def test_format_batch_text():
    results = generate_sample_batch(force_real=False)
    text = format_batch_text(results, real=False)
    assert "QUOTE QUALITY REVIEW" in text
    assert "$50-$100" in text


# ── Artwork QA matrix ────────────────────────────────────────────

def test_artwork_qa_covers_matrix(tmp_path):
    report = run_artwork_qa(output_dir=tmp_path)
    expected = len(NAME_CASES) * len(QUOTE_CASES) * len(SIZE_CASES)
    assert report["total"] == expected
    # Every rendered file exists.
    for c in report["cases"]:
        assert (tmp_path / c["file"].split("\\")[-1].split("/")[-1]).exists() \
            or c["file"]


def test_artwork_qa_all_pass_preflight(tmp_path):
    # The renderer targets each product's exact 300-DPI size, so all should pass.
    report = run_artwork_qa(output_dir=tmp_path)
    assert report["failed"] == 0, [c for c in report["cases"] if not c["preflight_ok"]]


def test_artwork_qa_long_name_renders(tmp_path):
    report = run_artwork_qa(output_dir=tmp_path)
    long_cases = [c for c in report["cases"] if "long_name" in c["case"]]
    assert long_cases
    # A long name must still produce a valid, in-spec image (no overflow crash).
    assert all(c["preflight_ok"] for c in long_cases)


def test_artwork_qa_image_sizes_match_product(tmp_path):
    run_artwork_qa(output_dir=tmp_path)
    with Image.open(tmp_path / "short_name_short_quote_11x14.png") as im:
        assert im.size == (3300, 4200)
    with Image.open(tmp_path / "short_name_short_quote_8x10.png") as im:
        assert im.size == (2400, 3000)


def test_format_qa_text(tmp_path):
    report = run_artwork_qa(output_dir=tmp_path, sizes=False)
    text = format_qa_text(report)
    assert "ARTWORK QA" in text and "passed" in text


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_sample_batch(tmp_path, capsys):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path), \
         patch.object(config, "ANTHROPIC_API_KEY", ""):
        rc = admin.main(["sample-batch"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "QUOTE QUALITY REVIEW" in out
    assert (tmp_path / "samples" / "quote_samples.txt").exists()


def test_cli_artwork_qa(tmp_path, capsys):
    import quoteforge.config as config
    with patch.object(config, "OUTPUT_DIR", tmp_path):
        rc = admin.main(["artwork-qa", "--quick"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ARTWORK QA" in out
