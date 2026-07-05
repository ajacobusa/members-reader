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
