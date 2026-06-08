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
