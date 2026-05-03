import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FIRST_NAME_ALIASES = {"first_name", "firstname", "first"}
LAST_NAME_ALIASES = {"last_name", "lastname", "last"}


def find_name_columns(fieldnames: list[str]) -> tuple[str, str]:
    """Detect first- and last-name column headers from a list of CSV field names.

    Recognised aliases — first: first_name, firstname, first
                         last:  last_name,  lastname,  last
    """
    first_col = next((h for h in fieldnames if h.strip().lower() in FIRST_NAME_ALIASES), None)
    last_col = next((h for h in fieldnames if h.strip().lower() in LAST_NAME_ALIASES), None)

    if not first_col:
        raise ValueError(
            f"No first-name column found. "
            f"Expected one of {sorted(FIRST_NAME_ALIASES)}. "
            f"Got: {fieldnames}"
        )
    if not last_col:
        raise ValueError(
            f"No last-name column found. "
            f"Expected one of {sorted(LAST_NAME_ALIASES)}. "
            f"Got: {fieldnames}"
        )

    return first_col, last_col


def read_members(csv_path: str | Path) -> list[dict]:
    """Read all rows from a CSV file and return them as a list of dicts.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of dicts, one per row, keyed by the CSV header names.

    Raises:
        FileNotFoundError: If *csv_path* does not exist.
        ValueError: If the file has no headers.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    logger.debug("Opening %s", path)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path} is empty or has no header row.")
        members = list(reader)

    logger.info("Read %d member(s) from %s", len(members), path)
    return members


def get_member_names(csv_path: str | Path) -> list[str]:
    """Return a list of full names ('First Last') from a CSV file.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of strings in 'First Last' format.

    Raises:
        FileNotFoundError: If *csv_path* does not exist.
        ValueError: If name columns cannot be detected.
    """
    members = read_members(csv_path)
    if not members:
        logger.warning("No rows found in %s", csv_path)
        return []

    first_col, last_col = find_name_columns(list(members[0].keys()))
    names = [f"{row[first_col]} {row[last_col]}" for row in members]
    logger.debug("Extracted %d name(s)", len(names))
    return names
