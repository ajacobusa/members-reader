"""Suite-wide guards.

docs/assets tripwire — every test must be hermetic (tmp_path only), but an
intermittent full-gate flake showed ~9 untracked images transiently appearing
in the REAL docs/assets mid-suite (then pruned by site-doctor's heal test),
tripping site-doctor's orphan_assets check. Static analysis could not name the
writer, so this autouse fixture catches it red-handed: any test that ADDS an
image to the real docs/assets fails ITSELF with the new filenames listed.
Removals are allowed (the site-doctor heal tests legitimately prune orphans).
"""
from pathlib import Path

import pytest

_ASSETS = Path(__file__).resolve().parent.parent / "docs" / "assets"
_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def _asset_images() -> set:
    try:
        return {f.name for f in _ASSETS.iterdir()
                if f.suffix.lower() in _IMG_EXT}
    except OSError:
        return set()


@pytest.fixture(autouse=True)
def _hermetic_runtime_uid_map(monkeypatch):
    """REGRESSION: once the operator's .env sets GELATO_UID_MAP_FILE (the
    documented go-live config, added 2026-07-11), the suite inherited 1,020
    REAL UIDs ambiently and every test assuming an empty runtime map failed.
    Tests must be hermetic against operator .env state: the runtime-map env is
    cleared here; a test that wants a map sets it explicitly (monkeypatch)."""
    monkeypatch.delenv("GELATO_UID_MAP", raising=False)
    monkeypatch.delenv("GELATO_UID_MAP_FILE", raising=False)


@pytest.fixture(autouse=True)
def _no_writes_to_real_docs_assets(request):
    """REGRESSION: name the test that pollutes the real docs/assets dir."""
    before = _asset_images()
    yield
    added = sorted(_asset_images() - before)
    if added:
        # Clean up so one polluter doesn't cascade into site-doctor failures,
        # then fail the guilty test loudly.
        for f in added:
            try:
                (_ASSETS / f).unlink()
            except OSError:
                pass
        pytest.fail(
            f"{request.node.nodeid} wrote image(s) into the REAL docs/assets "
            f"(tests must build into tmp_path): {added}")
