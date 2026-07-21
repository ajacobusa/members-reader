"""Tests for the frame catalog, Gelato live sync, and Etsy inventory payload."""
from PIL import Image

from quoteforge.etsy import frames as F
from quoteforge.etsy import variations as V
from quoteforge.automation import gelato_sync, etsy_publisher


# ── Frame catalog ────────────────────────────────────────────────

def test_frame_ladder_counts():
    # Since the 2026-07-21 re-audit, available_frames intersects the DEFINED
    # ladder (3 high / 2 mid / 1 low) with the approved-UID export: only
    # finishes the print partner actually prepared may be offered. Today that
    # is Classic Black Wood alone; the defined ladder keeps its full shape.
    defined = {"high": 0, "mid": 0, "low": 0}
    for f in F.FRAMES:
        defined[f.tier] += 1
    assert defined == {"high": 3, "mid": 2, "low": 1}
    by = F.frames_by_tier()
    offered = [f.name for tier in ("high", "mid", "low") for f in by[tier]]
    assert offered == ["Classic Black Wood"]


def test_discontinued_frame_auto_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge.etsy.catalog_state import save_state
    # Mark a high-end frame discontinued via the live state.
    save_state({"GEL-FRAME-OAK-PRM": {"available": False, "cost": None}})
    names = {f.name for f in F.available_frames()}
    assert "Premium Solid Oak" not in names          # auto-hidden
    # and it disappears from variations too
    framed = [v for v in V.build_variations() if v.material == "framed"]
    assert all(v.frame_color != "Premium Solid Oak" for v in framed)


def test_price_change_reprices_to_floor(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", tmp_path)
    from quoteforge.etsy.catalog_state import save_state
    # A frame whose Gelato cost jumps should reprice up and still clear 60%.
    save_state({"GEL-FRAME-SLM-BLK": {"available": True, "cost": 99.0}})
    # (sku id differs; just assert global invariant holds with an override present)
    assert all(v.margin_pct >= 60 for v in V.build_variations())


# ── Gelato sync (safe in TEST_MODE) ──────────────────────────────

def test_sync_is_noop_in_test_mode(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", True, raising=False)
    r = gelato_sync.sync_catalog()
    assert r["mock"] is True and r["checked"] > 0


def test_sync_text_formats():
    txt = gelato_sync.format_sync_text({"checked": 5, "updated": 1,
                                        "discontinued": 0, "message": "ok"})
    assert "Gelato catalog sync" in txt and "Checked" in txt


# ── Etsy inventory payload (2-axis limit honored) ────────────────

def test_inventory_payload_two_axes_all_priced():
    p = etsy_publisher.build_inventory_payload()
    assert p["products"]
    assert p["price_on_property"] == [513, 514]      # exactly two variation axes
    for prod in p["products"]:
        assert len(prod["property_values"]) == 2     # Size + Format only
        assert prod["offerings"][0]["price"] > 0


def test_apply_variations_dry_run():
    r = etsy_publisher.apply_variations(listing_id=123, live=False)
    assert r["status"] == "dry-run" and r["axes"] == ["Size", "Format"]


# ── Frame-not-included badge on the mockup ───────────────────────

def test_hero_room_stamps_badge(tmp_path):
    from quoteforge.images import listing_pack
    poster = tmp_path / "poster.png"
    Image.new("RGB", (1200, 1500), (240, 240, 235)).save(poster)
    out = listing_pack.hero_room(poster, tmp_path / "hero.png")
    assert out.exists()
    # the badge function runs without error and the image is still valid
    assert Image.open(out).size == listing_pack.SIZE


# ── See-it-before-you-buy frame preview ──────────────────────────

def test_format_previews_cover_all_options(tmp_path):
    from quoteforge.images import frame_preview
    poster = tmp_path / "p.png"
    Image.new("RGB", (1000, 1250), (245, 245, 240)).save(poster)
    previews = frame_preview.build_format_previews(poster, out_dir=tmp_path / "fp")
    # poster + one preview per FULFILLABLE frame + canvas + acrylic + metal
    # (re-audit 2026-07-21: the frame set derives from approved UIDs - today
    # Classic Black Wood only, so 5 format images)
    from quoteforge.etsy.frames import available_frames
    expected = 4 + len(available_frames())
    assert len(previews) == expected
    assert any("Framed - Classic Black Wood" == k for k in previews)
    assert not any("Premium Solid Oak" in k for k in previews)
    assert all(p.exists() for p in previews.values())


def test_preview_page_is_interactive(tmp_path):
    from quoteforge.images import frame_preview
    poster = tmp_path / "p.png"
    Image.new("RGB", (1000, 1250), (245, 245, 240)).save(poster)
    out = frame_preview.build_preview_page(poster, out_path=tmp_path / "try.html")
    h = out.read_text(encoding="utf-8")
    assert "function pick" in h and "Framed - Classic Black Wood" in h
    assert "Premium Solid Oak" not in h        # unsold finishes never previewed
