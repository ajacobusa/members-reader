# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`members-reader` — a Python library and CLI for reading member records from CSV files with automatic name-column detection. Zero runtime dependencies (standard library only). Python 3.10+.

## Directory Layout

```
src/members_reader/   # installable package
  __init__.py         # public API surface + __version__
  reader.py           # core logic: read_members, get_member_names, find_name_columns
  cli.py              # argparse CLI; entry point: members-reader
tests/
  conftest.py         # shared pytest fixtures (sample_csv, empty_csv, alternate_columns_csv)
  test_reader.py      # unit tests for reader.py
  test_cli.py         # unit tests for cli.py via main(argv)
examples/
  basic_usage.py      # runnable demo against members.csv
.github/workflows/
  ci.yml              # test matrix (3.10–3.12) + PyPI publish on version tag
```

## Commands

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_reader.py

# Run a single test by name
pytest -k "test_returns_full_names"

# Tests with coverage
pytest --cov=members_reader --cov-report=term-missing

# Run the CLI against the sample data
members-reader members.csv
members-reader members.csv --format json
members-reader members.csv --all-fields
```

## Publishing a Release

1. Bump `version` in `pyproject.toml` and `src/members_reader/__init__.py`
2. Commit, push, then `git tag vX.Y.Z && git push --tags`
3. CI builds and publishes to PyPI automatically (requires a PyPI Trusted Publisher configured in the `pypi` GitHub environment)

## Code Style

- Type-hint every function signature
- No runtime dependencies — standard library only
- Use `pathlib.Path` for all file operations
- Keep `FIRST_NAME_ALIASES` / `LAST_NAME_ALIASES` in `reader.py` as the single source of truth for supported column names
- Tests use `tmp_path` fixtures; never write to the project directory from tests
