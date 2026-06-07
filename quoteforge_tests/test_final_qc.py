"""Tests for the final QC gate (deterministic + AI-vision, TEST_MODE safe)."""
from PIL import Image


def test_final_qc_passes_good_art(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)  # AI skipped
    art = tmp_path / "good.png"
    Image.new("RGB", (3300, 4200), (20, 60, 40)).save(art)   # 11x14 @ 300dpi
    from quoteforge.images.final_qc import final_qc
    r = final_qc(art, "11x14 in")
    assert r["ok"] is True and r["ai"]["ok"] is True


def test_final_qc_blocks_low_res(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    art = tmp_path / "bad.png"
    Image.new("RGB", (300, 400), (20, 60, 40)).save(art)     # way too small
    from quoteforge.images.final_qc import final_qc
    r = final_qc(art, "11x14 in")
    assert r["ok"] is False and r["fails"]


def test_ai_vision_safe_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    from quoteforge.ai.assistant import ai_vision_check
    art = tmp_path / "x.png"; Image.new("RGB", (10, 10)).save(art)
    assert ai_vision_check(art)["ok"] is True
