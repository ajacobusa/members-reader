"""Proof->production parity gate, vendor_order_id column, and upload-endpoint
hardening (size limit + filename sanitization). The parity gate is the single
most expensive failure mode in the shop: the file the customer approved MUST
be byte-identical to the file sent to production."""
import hashlib
import io
from unittest.mock import patch

from PIL import Image


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _jpg(path, color=(120, 30, 30)):
    Image.new("RGB", (40, 40), color).save(path, "JPEG")
    return path


# ── vendor_order_id: honestly-named column, backfilled ───────────────

def test_vendor_order_id_column_backfilled_from_legacy(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "V1", "recipient_name": "A",
                           "occasion": "Birthday"})
    db.update_order(oid, gelato_order_id="LEGACY-9")
    db.init_db()                      # re-running migrations backfills
    assert db.get_order("V1")["vendor_order_id"] == "LEGACY-9"


def test_tracker_prefers_vendor_order_id(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    oid = db.create_order({"order_id": "V2", "etsy_order_id": "EV2",
                           "recipient_name": "B", "occasion": "Wedding"})
    db.update_order(oid, vendor="printify", vendor_order_id="P-NEW",
                    gelato_order_id="P-OLD", status="in_production")
    seen = []
    with patch("quoteforge.fulfillment.printify.get_order_status",
               side_effect=lambda vid: seen.append(vid) or
               {"status": "shipped", "tracking_number": "1Z1"}), \
         patch("quoteforge.automation.etsy_api.create_receipt_shipment",
               return_value={"status": "ok"}):
        from quoteforge.automation.fulfillment_tracker import sync_tracking
        sync_tracking()
    assert seen == ["P-NEW"]


# ── Proof -> production parity gate ──────────────────────────────────

def test_approval_stores_proof_file_hash(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    photo = _jpg(tmp_path / "photo.jpg")
    oid = db.create_order({"order_id": "H1", "recipient_name": "C",
                           "occasion": "Anniversary"})
    db.update_order(oid, print_file=str(photo))
    with patch("quoteforge.automation.pipeline_orchestrator."
               "resume_after_proof_approval", return_value={"ok": True}):
        from quoteforge.automation.customer_proof import record_customer_approval
        record_customer_approval("H1")
    expected = hashlib.sha256(photo.read_bytes()).hexdigest()
    o = db.get_order("H1")
    assert o["proof_approved"] == 1
    assert o["proof_file_hash"] == expected


def test_gelato_validation_blocks_file_changed_after_approval(tmp_path):
    from quoteforge.automation.print_quality import validate_order_for_gelato
    photo = _jpg(tmp_path / "p.jpg")
    approved_hash = hashlib.sha256(photo.read_bytes()).hexdigest()
    _jpg(photo, color=(0, 90, 0))          # file swapped after approval!
    order = {"recipient_address": {"name": "n", "address": "a", "city": "c",
                                   "postCode": "z", "country": "US"},
             "gelato_product_uid": "uid", "print_file": str(photo),
             "artwork_url": "https://x/y.png",
             "proof_file_hash": approved_hash}
    r = validate_order_for_gelato(order)
    assert not r["ok"]
    assert any("changed since" in i for i in r["issues"])


def test_gelato_validation_passes_matching_hash(tmp_path):
    from quoteforge.automation.print_quality import validate_order_for_gelato
    photo = _jpg(tmp_path / "p2.jpg")
    order = {"recipient_address": {"name": "n", "address": "a", "city": "c",
                                   "postCode": "z", "country": "US"},
             "gelato_product_uid": "uid", "print_file": str(photo),
             "artwork_url": "https://x/y.png",
             "proof_file_hash": hashlib.sha256(photo.read_bytes()).hexdigest()}
    assert validate_order_for_gelato(order)["ok"]


def test_gelato_validation_tolerates_orders_without_hash(tmp_path):
    """Orders approved before the parity feature must not be blocked."""
    from quoteforge.automation.print_quality import validate_order_for_gelato
    order = {"recipient_address": {"name": "n", "address": "a", "city": "c",
                                   "postCode": "z", "country": "US"},
             "gelato_product_uid": "uid", "artwork_url": "https://x/y.png"}
    assert validate_order_for_gelato(order)["ok"]


# ── Upload endpoint hardening ────────────────────────────────────────

def _client(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge.automation import webhook_server as ws
    ws.app.config["TESTING"] = True
    return ws.app.test_client()


def test_upload_rejects_traversal_filename(tmp_path, monkeypatch):
    """A filename like ..\\..\\evil.py must never escape the temp dir or be
    written with a non-image extension."""
    c = _client(tmp_path, monkeypatch)
    r = c.post("/upload", data={
        "email": "a@b.com",
        "file": (io.BytesIO(b"not an image"), "..\\..\\evil.py")})
    assert r.status_code == 400
    assert b"unsupported" in r.data.lower() or b"file type" in r.data.lower()
    assert not list(tmp_path.parent.glob("evil.py"))


def test_upload_rejects_oversized_file(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    big = io.BytesIO(b"\xff" * (26 * 1024 * 1024))     # > 25 MB cap
    r = c.post("/upload", data={"email": "a@b.com",
                                "file": (big, "big.jpg")})
    assert r.status_code in (400, 413)
    assert b"large" in r.data.lower() or r.status_code == 413


def test_upload_accepts_normal_jpg_and_files_under_client_id(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    buf = io.BytesIO()
    Image.new("RGB", (3000, 3000), (10, 10, 10)).save(buf, "JPEG")
    buf.seek(0)
    r = c.post("/upload", data={"email": "a@b.com", "size": "8x10",
                                "file": (buf, "family photo.jpg")})
    assert r.status_code == 200
    from quoteforge.customers import customer_id
    folder = tmp_path / "customers" / customer_id("a@b.com") / "uploads"
    assert folder.exists() and list(folder.glob("*family_photo.jpg"))
