"""Tests for the custom quote/photo listing copy."""
from quoteforge.etsy.custom_copy import (
    format_custom_copy, PHOTO_REQUIREMENTS, FAQ,
)
from quoteforge import admin


def test_copy_covers_quote_and_photo():
    text = format_custom_copy()
    assert "word-for-word" in text
    assert "PHOTO REQUIREMENTS" in text
    assert "screenshot" in text.lower()


def test_photo_requirements_list_sizes():
    for size in ["8x10", "11x14", "16x20", "18x24"]:
        assert size in PHOTO_REQUIREMENTS


def test_faq_has_quote_photo_proof():
    qs = " ".join(q for q, _ in FAQ).lower()
    assert "quote" in qs and "photo" in qs and "print" in qs


def test_copy_is_ascii_safe():
    format_custom_copy().encode("ascii")


def test_cli_custom_copy(capsys):
    rc = admin.main(["custom-copy"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "LISTING COPY" in out
