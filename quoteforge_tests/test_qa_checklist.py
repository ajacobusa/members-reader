"""E-commerce QA checklist - automatable items beyond the parity/hardening
suite: multi-upload, replace, transparency, orientation, design persistence,
approval persistence, and checkout gating."""
import io
import json

from PIL import Image


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _client(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge.automation import webhook_server as ws
    ws.app.config["TESTING"] = True
    return ws.app.test_client()


def _jpg_bytes(w=3000, h=3000):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 10, 10)).save(buf, "JPEG")
    buf.seek(0)
    return buf


# ── Functional: multiple uploads + replace ───────────────────────────

def test_multiple_uploads_kept_per_customer(tmp_path, monkeypatch):
    """Each upload (incl. a replacement) is preserved in the customer folder -
    nothing is silently overwritten, supporting audits and 'undo'."""
    c = _client(tmp_path, monkeypatch)
    for name in ("first.jpg", "second.jpg", "first.jpg"):   # 3rd replaces 1st
        r = c.post("/upload", data={"email": "multi@b.com", "size": "8x10",
                                    "file": (_jpg_bytes(), name)})
        assert r.status_code == 200
    from quoteforge.customers import customer_id
    ups = list((tmp_path / "customers" / customer_id("multi@b.com")
                / "uploads").glob("*.jpg"))
    assert len(ups) == 3


def test_transparent_png_accepted(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    buf = io.BytesIO()
    Image.new("RGBA", (3000, 3000), (10, 10, 10, 0)).save(buf, "PNG")
    buf.seek(0)
    r = c.post("/upload", data={"email": "t@b.com", "size": "8x10",
                                "file": (buf, "transparent.png")})
    assert r.status_code == 200
    assert json.loads(r.data)["decision"] in ("approve", "hold")


# ── Image processing: orientation ────────────────────────────────────

def test_portrait_and_landscape_both_validate(tmp_path):
    """Resolution is judged orientation-agnostically: a landscape photo for a
    portrait print (or vice versa) passes when the pixels suffice."""
    from quoteforge.automation.print_quality import validate_print_file
    portrait = tmp_path / "p.jpg"
    landscape = tmp_path / "l.jpg"
    Image.new("RGB", (1500, 1200), (9, 9, 9)).save(landscape, "JPEG")
    Image.new("RGB", (1200, 1500), (9, 9, 9)).save(portrait, "JPEG")
    assert validate_print_file(portrait, size="8x10")["ok"]
    assert validate_print_file(landscape, size="8x10")["ok"]


# ── Data integrity: design + approval persistence ────────────────────

def test_design_survives_refresh_and_approval_persists(tmp_path, monkeypatch):
    """A saved design is retrievable after a 'page refresh' (fresh fetch) and
    acceptance is recorded with a timestamp that persists."""
    db = _seed(tmp_path, monkeypatch)
    db.save_design("d@b.com", json.dumps({"wording": "Happy 40th, Sam!"}),
                   design_id="D1", summary="Framed 8x10")
    fetched = db.get_designs("d@b.com")          # fresh read = page refresh
    assert json.loads(fetched[0]["design_json"])["wording"] == "Happy 40th, Sam!"
    db.accept_design("d@b.com", "D1")
    again = db.get_designs("d@b.com")[0]
    assert again["accepted"] == 1 and again["accepted_at"]


# ── Checkout gating ──────────────────────────────────────────────────

def test_checkout_blocked_without_print_file():
    from quoteforge.automation.print_quality import validate_order_for_gelato
    r = validate_order_for_gelato({
        "recipient_address": {"name": "n", "address": "a", "city": "c",
                              "postCode": "z", "country": "US"},
        "gelato_product_uid": "uid"})
    assert not r["ok"] and any("print file" in i for i in r["issues"])


def test_checkout_blocked_when_quality_rejected():
    from quoteforge.automation.print_quality import validate_order_for_gelato
    r = validate_order_for_gelato({
        "recipient_address": {"name": "n", "address": "a", "city": "c",
                              "postCode": "z", "country": "US"},
        "gelato_product_uid": "uid", "artwork_url": "https://x/y.png",
        "print_quality": "reject"})
    assert not r["ok"] and any("quality" in i for i in r["issues"])
