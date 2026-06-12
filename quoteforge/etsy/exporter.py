"""CSV exporter for Etsy listing data, with timestamped backups."""
import csv
import shutil
from datetime import datetime
from pathlib import Path


def _backup_existing(csv_path: Path) -> None:
    """Copy existing CSV to a timestamped backup before overwriting."""
    if csv_path.exists():
        backup_dir = csv_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"etsy_listings_{timestamp}.csv"
        shutil.copy2(csv_path, backup_path)


def export_listings_csv(listings: list[dict], output_dir: Path) -> Path:
    """Write listing data to a CSV file ready for Etsy bulk review.

    Backs up the previous CSV to output_dir/backups/ before overwriting.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "etsy_listings.csv"
    _backup_existing(csv_path)
    fieldnames = ["quote", "title", "tags", "description", "category"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for listing in listings:
            row = dict(listing)
            row["tags"] = ", ".join(listing.get("tags", []))
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return csv_path
