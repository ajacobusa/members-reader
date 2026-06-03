import csv
from pathlib import Path
from quoteforge.etsy.exporter import export_listings_csv

def test_export_creates_csv(tmp_path):
    listings = [
        {
            "quote": "Rise above the storm.",
            "title": "Motivational Mountain Quote Wall Art",
            "tags": ["motivational poster", "wall art"],
            "description": "A stunning motivational wall art print.",
            "category": "Motivation & Mindset",
        }
    ]
    csv_path = export_listings_csv(listings, output_dir=tmp_path)
    assert csv_path.exists()
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["title"] == "Motivational Mountain Quote Wall Art"

def test_export_tags_joined_as_string(tmp_path):
    listings = [
        {
            "quote": "Test quote.",
            "title": "Test Title",
            "tags": ["tag one", "tag two", "tag three"],
            "description": "Test description.",
            "category": "Nature & Peace",
        }
    ]
    csv_path = export_listings_csv(listings, output_dir=tmp_path)
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert "tag one" in rows[0]["tags"]
