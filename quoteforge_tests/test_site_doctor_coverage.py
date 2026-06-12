"""Site Doctor coverage upgrades: whole-package docs ratchet (functions +
classes + module headers), corrupt-image render tripwire, wider regression set."""
from pathlib import Path

from PIL import Image

from quoteforge.automation import site_doctor as sd


# ── Docs ratchet: whole package, classes and module docstrings too ──────

def test_ratchet_guards_the_entire_package():
    """The ratchet must scan ALL of quoteforge/, not a hand-picked subset."""
    assert "quoteforge" in sd.CRITICAL_MODULES


def _write_module(tmp_path: Path, body: str) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir(exist_ok=True)
    f = pkg / "mod.py"
    f.write_text(body, encoding="utf-8")
    return tmp_path


def test_ratchet_flags_undocumented_function(tmp_path):
    root = _write_module(tmp_path, '"""Module doc."""\ndef f():\n    return 1\n')
    c = sd.check_docs_ratchet(modules=["pkg"], root=root)
    assert c["status"] == "FAIL" and "f" in c["detail"]


def test_ratchet_flags_undocumented_class(tmp_path):
    root = _write_module(tmp_path, '"""Module doc."""\nclass C:\n    pass\n')
    c = sd.check_docs_ratchet(modules=["pkg"], root=root)
    assert c["status"] == "FAIL" and "C" in c["detail"]


def test_ratchet_flags_missing_module_docstring(tmp_path):
    root = _write_module(tmp_path, 'def g():\n    """Doc."""\n    return 1\n')
    c = sd.check_docs_ratchet(modules=["pkg"], root=root)
    assert c["status"] == "FAIL" and "module docstring" in c["detail"]


def test_ratchet_passes_fully_documented_module(tmp_path):
    root = _write_module(
        tmp_path,
        '"""Module doc."""\n\n'
        'class C:\n    """Class doc."""\n\n'
        '    def m(self):\n        """Method doc."""\n        return 1\n')
    c = sd.check_docs_ratchet(modules=["pkg"], root=root)
    assert c["status"] == "OK", c["detail"]


# ── Rendering tripwire: every referenced image must decode ──────────────

def test_render_check_flags_corrupt_image(tmp_path):
    (tmp_path / "ok.png").parent.mkdir(exist_ok=True)
    Image.new("RGB", (4, 4), (10, 10, 10)).save(tmp_path / "ok.png")
    (tmp_path / "bad.png").write_bytes(b"not a real png at all")
    html = '<img src="assets/ok.png"><img src="assets/bad.png">'
    c = sd.check_assets_render(html, assets_dir=tmp_path)
    assert c["status"] == "FAIL" and "bad.png" in c["detail"]


def test_render_check_passes_valid_images(tmp_path):
    Image.new("RGB", (4, 4), (10, 10, 10)).save(tmp_path / "ok.png")
    html = '<img src="assets/ok.png">'
    c = sd.check_assets_render(html, assets_dir=tmp_path)
    assert c["status"] == "OK", c["detail"]


def test_render_check_runs_in_daily_page_checks():
    """The corrupt-image tripwire is part of the doctor's nightly page checks
    (and therefore healed by rebuild like any other page-level failure)."""
    names = [c["name"] for c in sd._page_checks(sd._read_page())]
    assert "assets_render" in names


# ── Regression subset: the personalization editor is covered nightly ────

def test_editor_tests_in_nightly_regression_subset():
    assert "quoteforge_tests/test_packages_exit.py" in sd.REGRESSION_TESTS
