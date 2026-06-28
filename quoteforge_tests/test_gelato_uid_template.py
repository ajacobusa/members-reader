"""Starter Gelato UID-map file generator: a complete blank checklist of every product
SKU, safe + re-runnable, preserving real values (no data loss) so it merges with
wallart-automap. Drives the go-live 'replace placeholder UIDs' step.
"""
import json


def test_template_lists_all_placeholder_skus(tmp_path, monkeypatch):
    import quoteforge.automation.gelato_sync as gs
    monkeypatch.setattr(gs, "_uid_map", lambda: {})        # isolate from any real env map
    from quoteforge.automation.gelato_uid_template import write_template
    path = tmp_path / "uidmap.json"
    r = write_template(str(path))
    assert r["total"] > 100 and r["mapped"] == 0 and r["remaining"] == r["total"]
    d = json.loads(path.read_text(encoding="utf-8"))
    assert all(k.upper().startswith("GEL-") for k in d)    # only GEL-* SKUs
    assert all(v == "" for v in d.values())                # all blank initially
    assert not any("+" in k for k in d)                    # no composite framed SKUs


def test_template_preserves_real_values_and_blanks_placeholders():
    from quoteforge.automation.gelato_uid_template import build_template
    out = build_template({"GEL-POSTER-8X10-STD": "real-us-poster-uid",   # real -> keep
                          "GEL-MUG-X": "GEL-MUG-X"})                      # placeholder -> blank
    assert out["GEL-POSTER-8X10-STD"] == "real-us-poster-uid"
    assert out["GEL-MUG-X"] == ""


def test_template_is_rerunnable_without_data_loss(tmp_path, monkeypatch):
    import quoteforge.automation.gelato_sync as gs
    monkeypatch.setattr(gs, "_uid_map", lambda: {})
    from quoteforge.automation.gelato_uid_template import write_template
    path = tmp_path / "uidmap.json"
    write_template(str(path))
    d = json.loads(path.read_text(encoding="utf-8"))
    key = next(iter(d))
    d[key] = "real-uid-123"                                 # owner fills one in
    path.write_text(json.dumps(d), encoding="utf-8")
    r = write_template(str(path))                           # re-run
    d2 = json.loads(path.read_text(encoding="utf-8"))
    assert d2[key] == "real-uid-123" and r["mapped"] == 1   # preserved, counted
