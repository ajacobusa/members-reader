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


# ── AI super-resolution provider wiring (mocked HTTP - no live key) ─────────
def _png_bytes(w, h):
    from io import BytesIO
    b = BytesIO()
    Image.new("RGB", (w, h), (130, 130, 130)).save(b, "PNG")
    return b.getvalue()


def _ai_config(monkeypatch, **over):
    """Turn the AI tier ON with a fake key (TEST_MODE off only for this test, then
    reverted by monkeypatch). photo_enhance never imports gelato_api, so this does
    not touch the live-API binding."""
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(cfg, "AI_PHOTO_ENHANCE", True)
    monkeypatch.setattr(cfg, "AI_UPSCALE_API_KEY", "test-key")
    monkeypatch.setattr(cfg, "AI_UPSCALE_API_URL", over.get("url", "http://sr/scale"))
    monkeypatch.setattr(cfg, "AI_UPSCALE_PROVIDER", over.get("provider", "generic"))
    monkeypatch.setattr(cfg, "AI_UPSCALE_MODEL", over.get("model", ""))


def test_generic_ai_provider_is_used(tmp_path, monkeypatch):
    # REGRESSION: with a generic SR endpoint configured, the AI upscaler is called
    # and its valid, big-enough output is used - method 'ai', not the baseline.
    _ai_config(monkeypatch)
    import requests
    big = _png_bytes(3200, 4000)

    class _R:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = big
    monkeypatch.setattr(requests, "post", lambda *a, **k: _R())
    p = _photo(tmp_path / "low.jpg", (1200, 1500))      # ~75 DPI @ 16x20
    res = enhance_to_print(p, "16x20", tmp_path)
    assert res["method"] == "ai" and res["ok"] is True


def test_replicate_provider_is_used(tmp_path, monkeypatch):
    # REGRESSION: the Replicate async path - create prediction, already succeeded,
    # download the output - yields method 'ai' at the 4x cap.
    _ai_config(monkeypatch, provider="replicate", url="", model="ver-123")
    import requests
    big = _png_bytes(3200, 4000)

    class _Post:
        status_code = 201

        @staticmethod
        def json():
            return {"status": "succeeded", "output": "http://rep/out.png",
                    "urls": {"get": "http://rep/poll"}}

    class _Get:
        status_code = 200
        content = big
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Post())
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Get())
    p = _photo(tmp_path / "low.jpg", (1200, 1500))
    res = enhance_to_print(p, "16x20", tmp_path)
    assert res["method"] == "ai" and res["ok"] is True


def test_bad_ai_response_falls_back_to_lanczos(tmp_path, monkeypatch):
    # REGRESSION: a provider returning garbage must NOT cost us the reliable Lanczos
    # baseline - we validate the bytes are a real image and fall back when not.
    _ai_config(monkeypatch)
    import requests

    class _R:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = b"this is not an image"
    monkeypatch.setattr(requests, "post", lambda *a, **k: _R())
    p = _photo(tmp_path / "low.jpg", (1800, 2400))
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert res["method"] == "lanczos" and res["ok"] is True


def test_undersized_ai_response_falls_back_to_lanczos(tmp_path, monkeypatch):
    # A valid but too-small AI result (below 0.9x target) is rejected -> Lanczos.
    _ai_config(monkeypatch)
    import requests
    tiny = _png_bytes(300, 375)

    class _R:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = tiny
    monkeypatch.setattr(requests, "post", lambda *a, **k: _R())
    p = _photo(tmp_path / "low.jpg", (1800, 2400))
    res = enhance_to_print(p, "18x24 in", tmp_path)
    assert res["method"] == "lanczos"


def test_ai_never_called_in_test_mode(tmp_path, monkeypatch):
    # Safety: even with a key set, TEST_MODE must keep the network untouched.
    import quoteforge.config as cfg, quoteforge.images.photo_enhance as pe
    monkeypatch.setattr(cfg, "AI_UPSCALE_API_KEY", "test-key")
    monkeypatch.setattr(cfg, "AI_UPSCALE_API_URL", "http://sr/scale")
    monkeypatch.setattr(cfg, "TEST_MODE", True)
    called = {"n": 0}
    monkeypatch.setattr(pe, "_upscale_generic",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    assert pe._ai_upscale(tmp_path, 100, 100, 2.0) is None
    assert called["n"] == 0
