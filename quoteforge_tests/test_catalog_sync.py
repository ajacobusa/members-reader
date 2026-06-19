"""Nightly Gelato catalog sync — local product DB, diff, validation, audit.

The invariants that protect production: TEST_MODE never calls Gelato (the local DB
is still rebuilt for review), the sync never overwrites the owner's custom data,
and nothing is fabricated (best sellers come from owner rank, not a fake badge).
"""
from PIL import Image

from quoteforge.automation import catalog_sync as cs


def _out(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)


# ── TEST_MODE: local rebuild, no Gelato call ─────────────────────

def test_sync_is_local_noop_in_test_mode(tmp_path, monkeypatch):
    # REGRESSION: in TEST_MODE the sync rebuilds the LOCAL product DB (so views
    # render for review) but never calls Gelato (_is_live() is False, so enrich is
    # a guarded no-op).
    _out(tmp_path, monkeypatch)
    assert cs._is_live() is False
    r = cs.sync_catalog_full(today="2026-06-18T07:20:00")
    assert r["live"] is False
    assert r["checked"] > 0
    assert cs._snapshot_path().exists()


def test_enrich_is_noop_when_not_live(tmp_path, monkeypatch):
    # REGRESSION: enrich_from_gelato makes no network call unless genuinely live.
    _out(tmp_path, monkeypatch)
    monkeypatch.setattr(cs, "_is_live", lambda: False)
    recs = {"m_tshirt": {"id": "m_tshirt", "image": ""}}
    out = cs.enrich_from_gelato(recs)
    assert out["m_tshirt"]["image"] == ""        # untouched


def test_build_local_catalog_has_both_genders(tmp_path, monkeypatch):
    _out(tmp_path, monkeypatch)
    recs = cs.build_local_catalog()
    assert recs, "expected a non-empty local catalog"
    assert any(r["gender"] == "men" for r in recs.values())
    assert any(r["gender"] == "women" for r in recs.values())
    tee = recs.get("m_tshirt")
    assert tee and tee["price"] > 0 and tee["colors"] and tee["sizes"]


# ── Diff detection ───────────────────────────────────────────────

def test_diff_detects_every_change_type():
    old = {
        "a": {"price": 10.0, "colors": ["White"], "sizes": ["M"], "image": "a.jpg"},
        "b": {"price": 20.0, "colors": ["White"], "sizes": ["M"], "image": "b.jpg"},
        "gone": {"price": 5.0, "colors": ["White"], "sizes": ["M"], "image": ""},
    }
    new = {
        "a": {"price": 12.0, "colors": ["White"], "sizes": ["M"], "image": "a.jpg"},
        "b": {"price": 20.0, "colors": ["White", "Teal"], "sizes": ["M", "XL"],
              "image": "b2.jpg"},
        "c": {"price": 9.0, "colors": ["Black"], "sizes": ["S"], "image": ""},
    }
    d = cs.diff_catalog(old, new)
    assert d["added"] == ["c"]
    assert "gone" in d["discontinued"]
    assert d["price_changes"] == [{"id": "a", "from": 10.0, "to": 12.0}]
    assert d["new_colors"] == [{"id": "b", "colors": ["Teal"]}]
    assert d["new_sizes"] == [{"id": "b", "sizes": ["XL"]}]
    assert "b" in d["image_changes"] and "b" in d["updated"]


def test_diff_flags_available_false_as_discontinued():
    old = {"a": {"available": True, "price": 1.0}}
    new = {"a": {"available": False, "price": 1.0}}
    assert "a" in cs.diff_catalog(old, new)["discontinued"]


# ── Image validation ─────────────────────────────────────────────

def test_validate_image_ok_and_failures(tmp_path):
    good = tmp_path / "m_tshirt.png"
    Image.new("RGB", (800, 1000), (255, 255, 255)).save(good)
    assert cs.validate_image(str(good), expect_id="m_tshirt")["ok"]
    # too small
    small = tmp_path / "tiny.png"
    Image.new("RGB", (50, 50)).save(small)
    assert not cs.validate_image(str(small))["ok"]
    # missing
    assert not cs.validate_image(str(tmp_path / "nope.png"))["ok"]
    # wrong mapping: filename doesn't match the expected product id
    other = tmp_path / "w_hoodie.png"
    Image.new("RGB", (800, 1000)).save(other)
    res = cs.validate_image(str(other), expect_id="m_tshirt")
    assert not res["ok"] and "maps to" in res["reason"]


def test_validate_images_returns_only_failures(tmp_path):
    ok = tmp_path / "m_tshirt.png"
    Image.new("RGB", (800, 1000)).save(ok)
    recs = {
        "m_tshirt": {"image": str(ok)},
        "m_tank": {"image": str(tmp_path / "missing.png")},
        "m_polo": {"image": ""},                    # no image -> skipped
    }
    fails = cs.validate_images(recs)
    assert [f["id"] for f in fails] == ["m_tank"]


# ── Preserve owner custom data ───────────────────────────────────

def test_apply_overrides_preserves_owner_data():
    recs = {"m_tshirt": {"id": "m_tshirt", "price": 25.0, "category": "auto"}}
    ov = {"m_tshirt": {"category": "Gifts for Him", "seo": "best dad tee",
                       "rank": 1, "description": "Owner copy"}}
    out = cs.apply_overrides(recs, ov)
    r = out["m_tshirt"]
    assert r["category"] == "Gifts for Him" and r["seo"] == "best dad tee"
    assert r["rank"] == 1 and r["description"] == "Owner copy"
    assert r["price"] == 25.0                        # catalog facts untouched


def test_sync_never_writes_overrides_file(tmp_path, monkeypatch):
    # REGRESSION: a sync must READ overrides, never write/clobber them.
    _out(tmp_path, monkeypatch)
    cs._catalog_dir().mkdir(parents=True, exist_ok=True)
    cs._overrides_path().write_text('{"m_tshirt": {"rank": 1}}', encoding="utf-8")
    cs.sync_catalog_full(today="2026-06-18T07:20:00")
    assert cs.load_overrides() == {"m_tshirt": {"rank": 1}}   # intact


# ── Derived views (honest by construction) ───────────────────────

def test_views_split_gender_and_dont_fabricate_bestsellers():
    recs = {
        "m_tshirt": {"gender": "men", "first_seen": "2020-01-01"},
        "w_tshirt": {"gender": "women", "first_seen": "2020-01-01"},
    }
    v = cs.build_catalog_views(recs, today="2026-06-18T00:00:00")
    assert len(v["mens"]) == 1 and len(v["womens"]) == 1
    assert v["best_sellers"] == []                   # no owner rank -> empty, honest
    assert v["new_arrivals"] == []                   # old products, not new


def test_new_arrivals_respect_first_seen_and_baseline():
    recs = {
        "fresh": {"gender": "men", "first_seen": "2026-06-10"},          # recent
        "old": {"gender": "men", "first_seen": "2024-01-01"},           # old
        "seed": {"gender": "men", "first_seen": "2026-06-10",
                 "baseline": True},                                      # baseline
    }
    v = cs.build_catalog_views(recs, today="2026-06-18T00:00:00")
    new_ids = [k for k, r in recs.items() if r in v["new_arrivals"]]
    assert new_ids == ["fresh"]                      # not old, not baseline seed


def test_bestsellers_use_owner_rank_order():
    recs = {
        "a": {"gender": "men", "rank": 2},
        "b": {"gender": "men", "rank": 1},
        "c": {"gender": "men"},                      # unranked -> excluded
    }
    v = cs.build_catalog_views(recs, today="2026-06-18T00:00:00")
    assert [r["rank"] for r in v["best_sellers"]] == [1, 2]


# ── First run vs incremental ─────────────────────────────────────

def test_first_run_is_baseline_not_new_arrivals(tmp_path, monkeypatch):
    _out(tmp_path, monkeypatch)
    r = cs.sync_catalog_full(today="2026-06-18T07:20:00")
    assert r["first_run"] is True
    snap = cs.load_snapshot()["products"]
    assert snap and all(rec.get("baseline") for rec in snap.values())
    assert cs.build_catalog_views(snap, today="2026-06-18T07:20:00")["new_arrivals"] == []


# ── Live enrichment (mocked) ─────────────────────────────────────

def test_enrich_sets_image_when_live(tmp_path, monkeypatch):
    _out(tmp_path, monkeypatch)
    monkeypatch.setattr(cs, "_is_live", lambda: True)
    import quoteforge.images.supplier_mockup as sm
    monkeypatch.setattr(sm, "gelato_blank_image",
                        lambda sku, **k: "https://cdn/real.png")
    recs = cs.build_local_catalog()
    cs.enrich_from_gelato(recs)
    assert any(r["image"] == "https://cdn/real.png" for r in recs.values())


# ── Audit text + admin command ───────────────────────────────────

def test_audit_text_has_the_required_sections():
    r = {"live": False, "synced_at": "2026-06-18T07:20:00", "checked": 39,
         "added": 2, "updated": 1, "discontinued": 0, "image_changes": 3,
         "price_changes": [{"id": "a", "from": 10, "to": 12}],
         "new_colors": [], "new_sizes": [], "image_failures": [],
         "first_run": False}
    t = cs.format_catalog_audit(r)
    for label in ("Products Added", "Products Updated", "Images Updated",
                  "Price Changes", "Sync Failures"):
        assert label in t
    assert "TEST_MODE" in t


def test_admin_catalog_sync_command(tmp_path, monkeypatch, capsys):
    _out(tmp_path, monkeypatch)
    from quoteforge import admin
    rc = admin.main(["catalog-sync"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "daily audit" in out and "Audit saved" in out
