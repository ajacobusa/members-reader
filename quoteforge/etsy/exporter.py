import csv
from pathlib import Path


def export_listings_csv(listings: list[dict], output_dir: Path) -> Path:
    """Write listing data to a CSV file ready for Etsy bulk review."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "etsy_listings.csv"
    fieldnames = ["quote", "title", "tags", "description", "category"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for listing in listings:
            row = dict(listing)
            row["tags"] = ", ".join(listing.get("tags", []))
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return csv_path
