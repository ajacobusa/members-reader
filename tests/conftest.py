import csv
import pytest
from pathlib import Path


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """CSV with two members and standard column names."""
    csv_file = tmp_path / "members.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "first_name", "last_name", "email"])
        writer.writeheader()
        writer.writerows([
            {"id": "1", "first_name": "Alice", "last_name": "Smith", "email": "alice@example.com"},
            {"id": "2", "first_name": "Bob", "last_name": "Jones", "email": "bob@example.com"},
        ])
    return csv_file


@pytest.fixture
def alternate_columns_csv(tmp_path: Path) -> Path:
    """CSV using 'firstname'/'lastname' instead of 'first_name'/'last_name'."""
    csv_file = tmp_path / "alt_members.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["firstname", "lastname"])
        writer.writeheader()
        writer.writerows([
            {"firstname": "Carol", "lastname": "White"},
        ])
    return csv_file


@pytest.fixture
def empty_csv(tmp_path: Path) -> Path:
    """CSV with headers but no data rows."""
    csv_file = tmp_path / "empty.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["first_name", "last_name"])
        writer.writeheader()
    return csv_file
