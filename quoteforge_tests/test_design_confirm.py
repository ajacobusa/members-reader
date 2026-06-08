"""Save design + accept/confirm email + storefront design controls."""
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


def test_save_and_get_design(fresh_db):
    db = fresh_db
    db.save_design("Buyer@X.com", design_json='{"fmt":"Canvas"}', design_id="d1",
                   summary="Canvas 8x10")
    ds = db.get_designs("buyer@x.com")
    assert len(ds) == 1 and ds[0]["design_id"] == "d1" and ds[0]["accepted"] == 0
    # upsert, no duplicate
    db.save_design("buyer@x.com", design_json='{"fmt":"Poster"}', design_id="d1")
    assert len(db.get_designs("buyer@x.com")) == 1


def test_accept_design(fresh_db):
    db = fresh_db
    db.save_design("a@b.com", design_id="d1")
    db.accept_design("a@b.com", "d1")
    assert db.get_designs("a@b.com")[0]["accepted"] == 1


def test_confirm_design_records_and_emails(fresh_db, monkeypatch):
    sent = {}
    def fake_send(subj, html, to=None, **k):
        sent["to"] = to; sent["subj"] = subj; return True
    monkeypatch.setattr("quoteforge.automation.emailer._send_email", fake_send)
    from quoteforge.automation.design_confirm import confirm_design
    r = confirm_design("c@d.com", summary="Canvas 8x10", design_id="d1")
    assert r["ok"] and r["emailed"] and sent["to"] == "c@d.com"
    assert fresh_db.get_designs("c@d.com")[0]["accepted"] == 1


def test_confirm_bad_email(fresh_db):
    from quoteforge.automation.design_confirm import confirm_design
    assert not confirm_design("nope", send=False)["ok"]


def test_design_and_confirm_endpoints(fresh_db, monkeypatch):
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    monkeypatch.setattr("quoteforge.automation.emailer._send_email",
                        lambda *a, **k: True)
    c = app.test_client()
    r = c.post("/design", json={"email": "x@y.com", "design": {"fmt": "Canvas"},
                                "summary": "Canvas 8x10"})
    assert r.status_code == 200 and r.get_json()["saved"]
    r2 = c.post("/confirm", json={"email": "x@y.com", "summary": "Canvas 8x10"})
    assert r2.status_code == 200 and r2.get_json()["status"] == "ok"
    bad = c.post("/design", json={"design": {}})
    assert bad.status_code == 400


def test_storefront_design_controls_in_page(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"; g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    h = out.read_text(encoding="utf-8")
    assert "function setTextRot" in h and "DRAGMODE==='photo'" in h
    assert "function saveDesign" in h and "function recheckPhotoRes" in h
    assert "function showFinalProof" in h and "function acceptProof" in h
    assert 'id="proofPop"' in h and "Add to basket" in h
    assert "function addToBasket" in h and "function proofAccept" in h
