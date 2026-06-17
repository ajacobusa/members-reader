"""AI-assisted photo enhancement: rescue a modestly-low-res buyer photo by
upscaling it to print resolution, then 100%-RE-REVIEW the result through the
same quality gate. The honesty invariant: a photo too small to rescue within the
upscale cap must still FAIL the re-review (so the buyer is asked for a better
one) — enhancement never fakes a blurry image up to a silent "pass".
"""
from PIL import Image

from quoteforge.images.photo_enhance import enhance_to_print
from quoteforge.images.photo_check import check_customer_photo


def _photo(path, size):
    Image.new("RGB", size, (120, 90, 60)).save(path, "JPEG")
    return path


def test_modestly_low_res_photo_is_rescued(tmp_path):
    # REGRESSION: a photo just under the floor (1800x2400 ≈ 100 DPI at 18x24)
    # upscales within the 2x baseline cap and now CLEARS the floor on re-review.
    p = _photo(tmp_path / "low.jpg", (1800, 2400))
    assert check_customer_photo(p, "18x24 in")["ok"] is False     # starts failing
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert res["ok"] is True
    assert res["method"] == "lanczos"          # offline baseline (no AI key)
    assert res["scale"] > 1.0
    assert res["review"]["ok"] is True and res["review"]["effective_dpi"] >= 120
    # the returned path is the bigger, enhanced file
    assert res["path"] != p
    with Image.open(res["path"]) as im:
        assert im.size[0] > 1800 and im.size[1] > 2400


def test_far_too_small_photo_is_not_faked(tmp_path):
    # REGRESSION: 500x700 at 18x24 needs >4x — beyond the cap. Enhancement must
    # NOT silently pass it: ok=False and the re-review still fails, so the order
    # still falls through to "send a better photo".
    p = _photo(tmp_path / "tiny.jpg", (500, 700))
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert res["ok"] is False
    assert res["path"] == p                    # original, not a fake-up
    assert res["review"]["ok"] is False


def test_already_good_photo_is_noop(tmp_path):
    p = _photo(tmp_path / "good.jpg", (3600, 4800))
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert res["ok"] is True and res["method"] == "none" and res["scale"] == 1.0
    assert res["path"] == p                    # untouched


def test_result_is_always_100pct_reviewed(tmp_path):
    # REGRESSION: every result carries the re-review of the image it returns -
    # nothing is accepted without passing through check_customer_photo.
    p = _photo(tmp_path / "low.jpg", (1800, 2400))
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert "review" in res and isinstance(res["review"], dict)
    # the review describes the path we hand back
    reviewed = check_customer_photo(res["path"], "18x24 in")
    assert reviewed["ok"] == res["review"]["ok"]


def test_missing_file_never_raises(tmp_path):
    res = enhance_to_print(tmp_path / "nope.jpg", "18x24 in", tmp_path)
    assert res["ok"] is False                  # no crash, just a clean fail


def test_kill_switch_disables_enhancement(tmp_path, monkeypatch):
    # REGRESSION: AI_PHOTO_ENHANCE=False restores the old behavior (bounce a
    # low-res photo, no enhancement attempt).
    monkeypatch.setattr("quoteforge.config.AI_PHOTO_ENHANCE", False)
    p = _photo(tmp_path / "low.jpg", (1800, 2400))
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert res["ok"] is False and res["method"] == "disabled"


def test_test_mode_uses_offline_baseline(tmp_path):
    # REGRESSION: with TEST_MODE on (default) and no AI key, enhancement uses the
    # local Lanczos baseline - never the network.
    from quoteforge import config
    assert config.TEST_MODE is True
    p = _photo(tmp_path / "low.jpg", (1800, 2400))
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert res["method"] in ("lanczos", "none")


def test_cli_enhance_photo(tmp_path, capsys):
    # REGRESSION: operators get an `enhance-photo` command that rescues a
    # borderline photo and reports the result.
    from quoteforge import admin
    p = _photo(tmp_path / "low.jpg", (1800, 2400))
    rc = admin.main(["enhance-photo", str(p), "18x24 in"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "RESCUED" in out and "lanczos" in out
