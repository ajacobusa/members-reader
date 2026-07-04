"""Owner real-photo override manifest (#realphotos): show the REAL product picture for
any SKU without going live, bypassing the imageless Gelato catalog API. Display-only."""
from quoteforge.images import supplier_mockup as sm


def _write(tmp_path, monkeypatch, text):
    f = tmp_path / "ovr.csv"
    f.write_text(text, encoding="utf-8")
    monkeypatch.setenv("PRODUCT_IMAGE_OVERRIDES_FILE", str(f))
    return f


def test_override_wins_in_test_mode(tmp_path, monkeypatch):
    # REGRESSION: an owner-supplied photo must show in TEST_MODE (bypass the gate +
    # the imageless catalog API) for a known SKU; an unknown SKU stays None.
    _write(tmp_path, monkeypatch, "sku,url\nGEL-M-TANK-XS-WHITE,https://cdn/x/tank.jpg\n")
    assert sm.gelato_blank_image("GEL-M-TANK-XS-WHITE") == "https://cdn/x/tank.jpg"
    assert sm.gelato_blank_image("GEL-UNKNOWN") is None      # no override, TEST_MODE -> None


def test_override_flows_through_apparel_tile_images(tmp_path, monkeypatch):
    # The editor reads APPAREL_COLOR_IMG built from apparel_tile_color_images; with an
    # override present it must surface in TEST_MODE (the function no longer early-returns).
    from quoteforge.images.supplier_mockup import apparel_photo_override_keys
    keys = apparel_photo_override_keys()
    assert keys, "expected apparel SKU keys"
    sku = keys[0]["sku"]
    _write(tmp_path, monkeypatch, f"sku,url\n{sku},https://cdn/x/real.jpg\n")
    colmap = sm.apparel_tile_color_images()
    # the override URL appears somewhere in the returned {garment:{color:url}} map
    urls = {u for cols in colmap.values() for u in cols.values()}
    assert "https://cdn/x/real.jpg" in urls


def test_no_manifest_is_a_clean_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("PRODUCT_IMAGE_OVERRIDES_FILE", str(tmp_path / "missing.csv"))
    assert sm.product_photo_overrides() == {}
    assert sm.apparel_tile_color_images() == {}              # TEST_MODE + no override -> empty


def test_bad_manifest_never_raises(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, "not,a,valid\nheader row\x00\n")
    assert isinstance(sm.product_photo_overrides(), dict)    # no exception


def test_non_http_url_is_ignored(tmp_path, monkeypatch):
    # a file:// or data: url must not be accepted (would break Gelato + could taint).
    _write(tmp_path, monkeypatch, "sku,url\nGEL-X,file:///etc/passwd\nGEL-Y,https://ok/y.jpg\n")
    ov = sm.product_photo_overrides()
    assert "GEL-X" not in ov and ov.get("GEL-Y") == "https://ok/y.jpg"


def test_override_keys_use_real_sku_format():
    rows = sm.apparel_photo_override_keys()
    assert rows and all(r["sku"] and r["garment"] and r["color"] for r in rows)


def test_admin_scaffold_writes_manifest(tmp_path, monkeypatch, capsys):
    from quoteforge import admin
    target = tmp_path / "ovr.csv"
    monkeypatch.setenv("PRODUCT_IMAGE_OVERRIDES_FILE", str(target))
    rc = admin.main(["photo-overrides", "scaffold"])
    assert rc == 0 and target.exists()
    body = target.read_text(encoding="utf-8")
    assert body.startswith("sku,url") and "GEL-" in body     # real SKU rows, blank urls
