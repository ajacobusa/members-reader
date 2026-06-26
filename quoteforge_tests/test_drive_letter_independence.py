"""REGRESSION: the project must be drive-letter-independent.

It runs from a USB drive whose letter changes when other devices are plugged in,
so nothing may hardcode a drive letter - the data dir must self-locate next to the
code, and the .env must be found relative to the code (not an absolute path).
"""
import importlib
from pathlib import Path


def test_output_dir_self_locates_next_to_code(monkeypatch):
    # With no OUTPUT_DIR override, the data dir resolves to <project_root>/data,
    # derived from config.py's own location - so it follows the drive's letter.
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    import quoteforge.config as c
    importlib.reload(c)
    try:
        expected = Path(c.__file__).resolve().parent.parent / "data"
        assert c.OUTPUT_DIR == expected
        # the resolved path carries whatever drive the code is on (no hardcoded letter)
        assert str(c.OUTPUT_DIR)[1:3] == ":\\" or str(c.OUTPUT_DIR).startswith("/")
    finally:
        importlib.reload(c)


def test_output_dir_env_override_still_wins(monkeypatch, tmp_path):
    # A server/explicit override is still honoured (persistent-disk deploys).
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "srv"))
    import quoteforge.config as c
    importlib.reload(c)
    try:
        assert c.OUTPUT_DIR == Path(str(tmp_path / "srv"))
    finally:
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        importlib.reload(c)


def test_env_file_is_located_relative_to_code():
    # .env is found via Path(__file__), never an absolute path, so it loads no
    # matter what drive letter the USB mounts as.
    src = (Path(__file__).resolve().parents[1] / "quoteforge" / "config.py").read_text(
        encoding="utf-8")
    assert "Path(__file__).resolve().parent.parent / \".env\"" in src
    assert "_PROJECT_ROOT" in src and "Path(__file__).resolve().parent.parent" in src
