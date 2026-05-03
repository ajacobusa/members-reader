# Contributing to members-reader

Thank you for taking the time to contribute.

## Development Setup

```bash
git clone https://github.com/ajacobusa/members-reader.git
cd members-reader
python -m venv venv
# Windows:  .\venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                            # full suite
pytest tests/test_reader.py       # single file
pytest -k "test_returns_full"     # single test by name
pytest --cov=members_reader       # with coverage report
```

All tests must pass before opening a pull request.

## Coding Standards

- Type-hint every function parameter and return value
- Keep the standard library the only runtime dependency
- Do not add comments that repeat what the code already says — only comment *why* when it's non-obvious
- Match the existing code style (no formatter is enforced, but be consistent)

## Adding Support for New Column Names

Name-column aliases live in `src/members_reader/reader.py`:

```python
FIRST_NAME_ALIASES = {"first_name", "firstname", "first"}
LAST_NAME_ALIASES  = {"last_name",  "lastname",  "last"}
```

Add your alias to the appropriate set and add a corresponding test in `tests/test_reader.py` under `TestFindNameColumns`.

## Pull Request Process

1. Fork the repository and create a branch from `main`
2. Make your changes and add or update tests
3. Ensure `pytest` passes locally
4. Open a pull request with a clear description of what changed and why

## Reporting Bugs

Open an issue at <https://github.com/ajacobusa/members-reader/issues> and include:
- Python version (`python --version`)
- A minimal CSV that reproduces the problem
- The full error traceback
