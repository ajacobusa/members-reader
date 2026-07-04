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
    # The recommended-resolution list must match the SOLD print sizes (#wallart): the
    # old list included 16x20 (never sold) and omitted 12x16 / 24x36 (both sold).
    for size in ["8x10", "11x14", "12x16", "18x24", "24x36"]:
        assert size in PHOTO_REQUIREMENTS
    assert "16x20" not in PHOTO_REQUIREMENTS          # not a sold print size


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
