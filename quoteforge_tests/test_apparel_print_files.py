"""Unit tests for the faithful apparel print-file hosting helper (#167 phase 2)."""
from quoteforge.images import apparel_print_files as apf


def _fake_public(path):
    return {"url": f"https://cdn/{path}", "public": True}


def test_front_is_artwork_and_extras_are_extra_files(monkeypatch):
    # front -> front_url (Gelato 'default'); back/sleeves -> extra_files placements.
    monkeypatch.setattr("quoteforge.automation.file_host.publish_print_file", _fake_public)
    out = apf.build_apparel_print_files({
        "front": "f.png", "back": "b.png",
        "sleeve-left": "sl.png", "sleeve-right": "sr.png"})
    assert out["front_url"] == "https://cdn/f.png"
    assert out["extra_files"] == {"back": "https://cdn/b.png",
                                  "sleeve-left": "https://cdn/sl.png",
                                  "sleeve-right": "https://cdn/sr.png"}
    assert set(out["hosted"]) == {"front", "back", "sleeve-left", "sleeve-right"}
    assert out["all_public"] is True


def test_unknown_side_is_ignored_never_guessed(monkeypatch):
    # A stray side must NOT silently become a wrong placement.
    monkeypatch.setattr("quoteforge.automation.file_host.publish_print_file", _fake_public)
    out = apf.build_apparel_print_files({"front": "f.png", "collar": "c.png"})
    assert out["front_url"] == "https://cdn/f.png"
    assert out["extra_files"] == {}
    assert "collar" not in out["hosted"]


def test_missing_or_empty_paths_are_skipped(monkeypatch):
    monkeypatch.setattr("quoteforge.automation.file_host.publish_print_file", _fake_public)
    out = apf.build_apparel_print_files({"front": "", "back": None, "sleeve-left": "sl.png"})
    assert out["front_url"] == "" and out["extra_files"] == {"sleeve-left": "https://cdn/sl.png"}


def test_non_public_url_sets_all_public_false(monkeypatch):
    # A local:// fallback (not fetchable by Gelato) must be reported so the router's
    # public-URL guard can hold the order for manual instead of handing over a bad URL.
    def _local(path):
        return {"url": f"file:///{path}", "public": False}
    monkeypatch.setattr("quoteforge.automation.file_host.publish_print_file", _local)
    out = apf.build_apparel_print_files({"front": "f.png"})
    assert out["front_url"] == "file:///f.png" and out["all_public"] is False


def test_empty_input_is_a_clean_noop():
    out = apf.build_apparel_print_files({})
    assert out == {"front_url": "", "extra_files": {}, "hosted": [], "all_public": True}


def test_sleeveless_garment_drops_sleeve_print_files(monkeypatch):
    # REGRESSION (L-1 defense-in-depth): build_apparel_print_files must never host a
    # sleeve file for a sleeveless garment, even if a caller passes one - you can't print
    # a sleeve that doesn't exist. The frontend gates this too; this is the backend backstop.
    monkeypatch.setattr("quoteforge.automation.file_host.publish_print_file", _fake_public)
    out = apf.build_apparel_print_files({"front": "f.png", "sleeve-left": "sl.png", "sleeve-right": "sr.png"},
                   has_sleeves=False)
    assert out["front_url"] == "https://cdn/f.png"
    assert out["extra_files"] == {}                       # sleeves dropped
    assert "sleeve-left" not in out["hosted"] and "sleeve-right" not in out["hosted"]
    # a sleeved garment (default) still hosts them
    out2 = apf.build_apparel_print_files({"front": "f.png", "sleeve-left": "sl.png"})
    assert out2["extra_files"] == {"sleeve-left": "https://cdn/sl.png"}


def test_phase2c_upload_decode_store_and_read_back(tmp_path, monkeypatch):
    # #167 Phase 2c end-to-end backend chain: decode a real PNG data-URI -> save to disk
    # -> store on the saved design -> read back for the linked order. Rejects a non-PNG
    # side and an unknown side (hardened, never guessed).
    import base64, io
    from pathlib import Path
    from PIL import Image
    from quoteforge.db import database as db
    import quoteforge.config as cfg
    from quoteforge.images.apparel_print_files import save_print_file_datauris
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(cfg, "OUTPUT_DIR", tmp_path, raising=False)
    db.init_db()
    buf = io.BytesIO(); Image.new("RGBA", (4, 4), (255, 0, 0, 128)).save(buf, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    paths = save_print_file_datauris("a@b.com", "default", {
        "front": uri, "back": uri,
        "collar": uri,                       # unknown side -> rejected
        "sleeve-left": "data:text/plain,x"})  # non-PNG -> rejected
    assert set(paths) == {"front", "back"}
    assert all(Path(p).exists() for p in paths.values())
    # store on a design, link an order, read back
    db.save_design("a@b.com", design_json="{}", design_id="default")
    db.set_design_print_files("a@b.com", "default", paths)
    db.link_design_to_order("a@b.com", "ORD-1")
    assert set(db.design_print_files_for_order("ORD-1")) == {"front", "back"}
    assert db.design_print_files_for_order("NOPE") == {}
