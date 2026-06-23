"""Wedding/Corporate packages (margin-safe) + exit-intent capture + /signup."""


def test_all_packages_hold_margin_floor():
    from quoteforge.etsy.packages import all_packages
    from quoteforge.etsy.variations import floor_for_tier
    pkgs = all_packages()
    assert len(pkgs) >= 4
    for p in pkgs:
        assert p["holds_floor"], f"{p['name']} breaks floor"
        assert p["margin_pct"] >= 60
        assert p["from_total"] > 0 and p["per_piece"] > 0


def test_packages_have_both_audiences():
    from quoteforge.etsy.packages import all_packages
    auds = {p["audience"] for p in all_packages()}
    assert {"wedding", "corporate"} <= auds


def test_packages_and_exit_in_page(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert "Wedding &amp; corporate packages" in h and "Request this package" in h
    assert "id=\"exitpop\"" in h and "function submitExit" in h
    assert "{packages_html}" not in h


def test_signup_endpoint_adds_subscriber(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    import pytest
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    client = app.test_client()
    r = client.post("/signup", json={"email": "buyer@example.com", "source": "exit_intent"})
    assert r.status_code == 200 and r.get_json()["status"] == "ok"
    bad = client.post("/signup", json={"email": "nope"})
    assert bad.status_code == 400


def test_bundle_discount_js_matches_backend_single_source(tmp_path):
    """The storefront discount tiers must be injected from variations.QTY_DISCOUNT,
    not hardcoded (prevents JS/Python drift)."""
    import json
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    from quoteforge.etsy.variations import QTY_DISCOUNT
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    expected = json.dumps([[t, d] for t, d in QTY_DISCOUNT])
    assert f"const QD = {expected};" in h
    # the old hardcoded ternary must be gone
    assert "n>=4?0.15:n>=3?0.12" not in h
    # promo copy comes from config
    from quoteforge.config import PROMO_WELCOME_CODE
    assert PROMO_WELCOME_CODE in h


def test_guided_bundle_flow_present(tmp_path):
    """The bundle builder must route through a per-design personalize flow before
    items reach the cart (not a blind add)."""
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert "function startBundleFlow" in h and "function nextBundleStep" in h
    assert 'id="bundlebanner"' in h and "Personalize &amp; add this set" in h
    # add-to-order advances the guided flow
    assert "if(BFLOW){{ BFLOW.idx++; nextBundleStep(); }}" in h or \
           "if(BFLOW){ BFLOW.idx++; nextBundleStep(); }" in h


def test_single_item_review_and_photo_guard(tmp_path):
    """Single-item add shows a live 'review before adding' summary and guards a
    too-low-res uploaded photo (review at the moment of adding, no extra screen)."""
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert 'id="mreview"' in h and "function updateReview" in h
    assert "Review before adding" in h
    assert "too low-resolution" in h  # photo guard in addToOrder


def test_uploaded_photo_previews_on_canvas(tmp_path):
    """An uploaded photo must render in the live preview (canvas background),
    not only get a quality check."""
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert "let PHOTO=null" in h and "ctx.drawImage(PHOTO" in h
    # The photo previews on canvas regardless of resolution; the upload now shows the
    # AI Smart-review card (with a remove link) instead of the old inline message.
    assert "function removePhoto" in h and "renderPhotoReview" in h


def test_text_drag_and_size_controls(tmp_path):
    """Wording must be draggable and have a manual font-size control."""
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert "function initTextDrag" in h and "let TPOS=" in h
    assert "function setTextSize" in h and 'id="mtsize"' in h
    assert "drag the wording on the preview to move it" in h
    assert "function resetTextPos" in h
