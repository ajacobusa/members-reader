# members-reader

A lightweight Python library and CLI for reading member records from CSV files. Automatically detects first- and last-name columns so it works with your existing data without any configuration.

## Features

- **Zero dependencies** — pure Python standard library
- **Auto-detects name columns** (`first_name`, `firstname`, `first`, and their `last_` equivalents)
- **Library + CLI** — use it in code or from the terminal
- **Full type hints** throughout
- **Structured logging** — integrate with your application's log config

---

## Installation

```bash
pip install members-reader
```

Or install directly from GitHub:

```bash
pip install git+https://github.com/ajacobusa/members-reader.git
```

---

## Quick Start

### As a library

```python
from members_reader import get_member_names, read_members

# Get a list of "First Last" strings
names = get_member_names("members.csv")
print(names)  # ["Alice Smith", "Bob Jones", ...]

# Get all fields as a list of dicts
members = read_members("members.csv")
print(members[0])  # {"id": "1", "first_name": "Alice", "last_name": "Smith", "email": "..."}
```

### As a CLI

```bash
# Print names (one per line)
members-reader members.csv

# Output as JSON
members-reader members.csv --format json

# Output all CSV fields
members-reader members.csv --all-fields

# Combine flags
members-reader members.csv --all-fields --format json

# Enable debug logging
members-reader members.csv --verbose
```

---

## API Reference

### `read_members(csv_path) -> list[dict]`

Reads every row from a CSV file and returns them as a list of dicts keyed by header name.

| Parameter | Type | Description |
|-----------|------|-------------|
| `csv_path` | `str \| Path` | Path to the CSV file |

**Raises**
- `FileNotFoundError` — file does not exist
- `ValueError` — file has no header row

---

### `get_member_names(csv_path) -> list[str]`

Returns a list of full names in `"First Last"` format.

| Parameter | Type | Description |
|-----------|------|-------------|
| `csv_path` | `str \| Path` | Path to the CSV file |

**Raises**
- `FileNotFoundError` — file does not exist
- `ValueError` — cannot detect name columns

---

### `find_name_columns(fieldnames) -> tuple[str, str]`

Given a list of CSV header names, returns the `(first_col, last_col)` pair.

Recognised aliases:

| Meaning | Accepted values |
|---------|----------------|
| First name | `first_name`, `firstname`, `first` |
| Last name | `last_name`, `lastname`, `last` |

**Raises**
- `ValueError` — a required column is missing

---

## CSV Format

Any CSV with a recognised first- and last-name column works. Extra columns are ignored.

```csv
id,first_name,last_name,email,gender
1,Alice,Smith,alice@example.com,Female
2,Bob,Jones,bob@example.com,Male
```

---

## Logging

`members-reader` uses Python's standard `logging` module under the `members_reader` namespace. Plug it into your application's log configuration:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from members_reader import get_member_names
names = get_member_names("members.csv")
# DEBUG members_reader.reader: Opening members.csv
# INFO  members_reader.reader: Read 500 member(s) from members.csv
```

---

## Error Handling

```python
from pathlib import Path
from members_reader import get_member_names

try:
    names = get_member_names(Path("members.csv"))
except FileNotFoundError as e:
    print(f"File missing: {e}")
except ValueError as e:
    print(f"Bad CSV structure: {e}")
```

---

## Development Setup

```bash
git clone https://github.com/ajacobusa/members-reader.git
cd members-reader
python -m venv venv
# Windows:  .\venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"
```

Run tests:

```bash
pytest                          # all tests
pytest tests/test_reader.py     # single file
pytest --cov=members_reader     # with coverage
```

---

## Publishing a Release

1. Bump `version` in `pyproject.toml` and `src/members_reader/__init__.py`
2. Commit and push
3. Create a tag: `git tag v0.2.0 && git push --tags`
4. The CI workflow automatically builds and publishes to PyPI

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
