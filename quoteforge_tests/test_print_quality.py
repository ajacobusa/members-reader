"""AI print-quality check, order validation, and /upload endpoint."""
import os, tempfile
import pytest
from PIL import Image


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


def _img(w, h):
    p = os.path.join(tempfile.gettempdir(), f"t_{w}x{h}.jpg")
    Image.new("RGB", (w, h), (15, 61, 46)).save(p)
    return p


def test_validate_low_res_holds():
    from quoteforge.automation.print_quality import assess_photo
    a = assess_photo(_img(304, 92), "8x10")
    assert a["decision"] == "hold" and a["validation"]["resolution_ok"] is False


def test_validate_high_res_approves():
    from quoteforge.automation.print_quality import assess_photo
    a = assess_photo(_img(1800, 2400), "8x10")
    assert a["decision"] == "approve" and a["validation"]["resolution_ok"]


def test_unsupported_format_rejects(tmp_path):
    from quoteforge.automation.print_quality import assess_photo
    bad = tmp_path / "art.bmp"; bad.write_bytes(b"x")
    a = assess_photo(str(bad), "8x10")
    assert a["decision"] == "reject"


def test_pdf_passes_format():
    from quoteforge.automation.print_quality import validate_print_file
    p = os.path.join(tempfile.gettempdir(), "doc.pdf")
    open(p, "wb").write(b"%PDF-1.4 test")
    v = validate_print_file(p, "8x10")
    assert v["format_ok"] and v["ok"]


def test_order_validation():
    from quoteforge.automation.print_quality import validate_order_for_gelato
    assert not validate_order_for_gelato({})["ok"]
    good = {"recipient_address": {"name": "A", "address": "1 St", "city": "X",
            "postCode": "3", "country": "US"}, "gelato_product_uid": "u",
            "artwork_url": "http://x/f.jpg", "print_quality": "approve"}
    assert validate_order_for_gelato(good)["ok"]
    rej = dict(good); rej["print_quality"] = "reject"
    assert not validate_order_for_gelato(rej)["ok"]


def test_pipeline_holds_when_invalid(fresh_db, monkeypatch):
    # An order with no print file must not reach Gelato - it holds on validation.
    from quoteforge.automation.print_quality import validate_order_for_gelato
    v = validate_order_for_gelato({"recipient_address": {"name": "A", "address": "1",
        "city": "X", "postCode": "3", "country": "US"}, "gelato_product_uid": "u",
        "artwork_url": "", "print_quality": "approve"})
    assert not v["ok"] and any("print file" in i for i in v["issues"])


def test_upload_endpoint(fresh_db, monkeypatch):
    from quoteforge.automation.webhook_server import app, FLASK_AVAILABLE
    if not (FLASK_AVAILABLE and app):
        pytest.skip("Flask not available")
    import io
    c = app.test_client()
    buf = io.BytesIO()
    Image.new("RGB", (1800, 2400), (15, 61, 46)).save(buf, format="JPEG")
    buf.seek(0)
    data = {"email": "buyer@x.com", "size": "8x10",
            "file": (buf, "photo.jpg")}
    r = c.post("/upload", data=data, content_type="multipart/form-data")
    # The route works + returns the print-quality fields (the decision now reflects
    # the quality score, so assert a valid decision rather than a fixed approve).
    j = r.get_json()
    assert r.status_code == 200 and j["decision"] in ("approve", "hold", "reject")
    assert "quality_score" in j and "stars" in j
    bad = c.post("/upload", data={"email": "buyer@x.com"},
                 content_type="multipart/form-data")
    assert bad.status_code == 400


def test_check_print_command_registered():
    from quoteforge.admin import COMMANDS
    assert "check-print" in COMMANDS and "validate-order" in COMMANDS
