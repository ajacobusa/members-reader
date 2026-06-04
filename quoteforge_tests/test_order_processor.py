import csv
from pathlib import Path
from unittest.mock import patch, MagicMock

from quoteforge.etsy.order_processor import (
    ETSY_PERSONALIZATION_FORM,
    NICHE_LISTING_TITLES,
    NICHE_TAGS,
    process_order,
    _log_order,
)
from quoteforge.etsy.bulk_catalog import generate_bulk_catalog, generate_seo_pack


def test_etsy_form_has_required_fields():
    required = ["Recipient Name", "Occasion", "Relationship", "Scenery", "Memory"]
    for field in required:
        assert field in ETSY_PERSONALIZATION_FORM, f"Missing field: {field}"


def test_niche_titles_not_empty():
    assert len(NICHE_LISTING_TITLES) >= 6
    for niche, titles in NICHE_LISTING_TITLES.items():
        assert len(titles) >= 1, f"{niche} has no titles"


def test_niche_tags_have_13_or_fewer():
    for niche, tags in NICHE_TAGS.items():
        assert len(tags) <= 13, f"{niche} has more than 13 tags"


def test_log_order_creates_csv(tmp_path):
    with patch("quoteforge.etsy.order_processor.OUTPUT_DIR", tmp_path):
        _log_order(
            recipient_name="Emma",
            sender_name="Mom",
            relationship="To My Daughter",
            occasion="Graduation",
            scenery="Mountains",
            output_style="Personal Letter",
            saved_dir=str(tmp_path),
        )
    log_path = tmp_path / "order_log.csv"
    assert log_path.exists()
    with log_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["recipient_name"] == "Emma"


def test_generate_bulk_catalog(tmp_path):
    with patch("quoteforge.etsy.bulk_catalog.OUTPUT_DIR", tmp_path):
        path = generate_bulk_catalog(quotes_per_relationship=5)
    assert path.exists()
    with path.open() as f:
        rows = list(csv.DictReader(f))
    # 8 relationships × 5 quotes each = 40 rows
    assert len(rows) == 40
    relationships = {r["relationship"] for r in rows}
    assert "Daughter" in relationships
    assert "Son" in relationships
    assert "Graduation" in relationships


def test_bulk_catalog_has_seo_columns(tmp_path):
    with patch("quoteforge.etsy.bulk_catalog.OUTPUT_DIR", tmp_path):
        path = generate_bulk_catalog(quotes_per_relationship=2)
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert all("etsy_title" in r for r in rows)
    assert all("etsy_tags" in r for r in rows)
    assert all(len(r["etsy_title"]) > 10 for r in rows)


def test_generate_seo_pack_returns_dict():
    pack = generate_seo_pack("Personalized Daughter Gifts")
    assert "titles" in pack
    assert "tags" in pack
    assert "description_starters" in pack
    assert len(pack["tags"]) <= 13
    assert all(len(tag) <= 20 for tag in pack["tags"])


def test_generate_seo_pack_unknown_niche():
    pack = generate_seo_pack("Unknown Niche XYZ")
    assert isinstance(pack["titles"], list)
    assert len(pack["titles"]) >= 1
