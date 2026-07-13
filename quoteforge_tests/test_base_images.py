"""Base images: the named, owner-updatable registry of REAL product photos
(config/base_images.json) that feeds the per-colour display path.

Grounded end to end: the owner `add`s a photographed colour -> the registry
records it -> the build emits it into APPAREL_COLOR_IMG -> the editor/spin/tile
show the REAL product for that colour. Colours are verified against the real
Gelato catalog (fulfillable facets) before they can be registered - never offer
a photo for a colour the print partner can't make. No fabrication: the only
photo source is a file the owner supplies.
"""
import json
import re

from PIL import Image


def _page(tmp_path) -> str:
    """Render the shop home with the customizer on, same harness as test_ux_editor."""
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "h.html", frame_picker=True)
    return out.read_text(encoding="utf-8")


def _color_img(h: str) -> dict:
    m = re.search(r"const APPAREL_COLOR_IMG = (\{.*?\});", h)
    assert m, "APPAREL_COLOR_IMG missing from the page"
    return json.loads(m.group(1))


# ── the registry (config/base_images.json) ─────────────────────────────────

def _real_registry(monkeypatch):
    """Point at the OPERATOR registry (config/base_images.json) - the conftest
    default is a frozen fixture so page builds stay fast and hermetic."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent / "config" / "base_images.json"
    monkeypatch.setenv("BASE_IMAGES_FILE", str(repo))


def test_registry_seed_census_and_files_exist(monkeypatch):
    _real_registry(monkeypatch)
    # REGRESSION: the eyeball-verified photo-colour census must live in the
    # owner-editable registry (not hardcoded in listing_preview), every entry's
    # file must exist, and the known census facts must hold: w_tshirt was shot
    # in Heather Grey (NOT white), raglans are two-tone ('' = never match).
    from quoteforge.images import base_images as bi
    reg = bi.load_registry()
    assert reg.get("version") == 1 and isinstance(reg.get("images"), list)
    # census = the SIDE photos only; percolor entries (real exports or
    # simulated tints) share the (gid, side) key and must not shadow them
    entries = {(e["garment_id"], e["side"]): e for e in reg["images"]
               if not e.get("percolor")}
    assert entries[("m_hoodie", "front")]["color"] == "White"
    assert entries[("w_tshirt", "front")]["color"] == "Heather Grey"
    assert entries[("w_tshirt", "back")]["color"] == "Heather Grey"
    assert entries[("m_raglan", "front")]["color"] == ""
    assert entries[("w_raglan", "front")]["color"] == ""
    for e in reg["images"]:
        assert bi.resolve_file(e).exists(), f"missing base image file: {e['file']}"


def test_side_photo_colour_comes_from_registry(tmp_path, monkeypatch):
    # REGRESSION: APPAREL_SIDE_IMG.color is driven by the registry - edit the
    # registry, rebuild, the editor's colour match follows. No more hardcode.
    monkeypatch.setenv("BASE_IMAGES_FILE", str(tmp_path / "reg.json"))
    (tmp_path / "reg.json").write_text(json.dumps({"version": 1, "images": [
        {"garment_id": "m_hoodie", "color": "Sand", "side": "front",
         "file": "brand/tile-m_hoodie.jpg", "source": "dashboard_export",
         "added": "2026-07-10"}]}), encoding="utf-8")
    h = _page(tmp_path)
    m = re.search(r"const APPAREL_SIDE_IMG = (\{.*?\});", h)
    d = json.loads(m.group(1))
    assert d["m_hoodie"]["color"] == "Sand"          # registry-driven
    assert d["m_tshirt"]["color"] == ""              # unregistered -> never match


# ── end-to-end: owner adds a colour -> that colour shows its real photo ────

def test_add_navy_flows_to_percolor_map_end_to_end(tmp_path, monkeypatch):
    # REGRESSION (the whole feature): admin-adding a Navy base image must make
    # Navy - and ONLY Navy - resolve a real per-colour photo in the built page.
    # Uncovered colours (e.g. Sand) must NOT inherit any photo: partial coverage
    # never re-introduces the "white photo for a Navy pick" bug.
    from quoteforge.images import base_images as bi
    monkeypatch.setenv("BASE_IMAGES_FILE", str(tmp_path / "reg.json"))
    src = tmp_path / "export.jpg"
    Image.new("RGB", (900, 1000), (28, 38, 74)).save(src)   # a navy garment shot
    res = bi.add_image(src, "m_hoodie", "Navy", dest_dir=tmp_path / "brand")
    assert res.get("ok"), res
    assert (tmp_path / "brand" / "base-m_hoodie-navy.jpg").exists()
    reg = bi.load_registry()
    assert any(e["garment_id"] == "m_hoodie" and e["color"] == "Navy"
               for e in reg["images"])
    h = _page(tmp_path)
    cmap = _color_img(h)
    assert "Navy" in cmap.get("m_hoodie", {}), "Navy photo missing from the map"
    # re-hosted same-origin: an emitted asset file or an inline data-URI - never
    # a raw supplier/absolute URL that would leak or taint the canvas
    assert cmap["m_hoodie"]["Navy"].startswith(("assets/", "data:image/"))
    assert "Sand" not in cmap.get("m_hoodie", {})           # uncovered stays uncovered


def test_front_standin_is_colour_exact(tmp_path):
    # REGRESSION (honesty under partial coverage): once ANY per-colour photo
    # exists, the old gate let the colour-agnostic side photo stand in for every
    # OTHER colour's front (Sand would show the white studio shot). The FRONT
    # stand-in must be colour-exact; only the BACK view may use the side back
    # photo when per-colour fronts exist.
    h = _page(tmp_path)
    assert "if(!_u && (_photoColorMatch || (_side==='back'&&_hasColorPhotos)))" in h
    assert "if(!url && sm && photoMatch) url=sm.front||'';" in h   # spin front too


# ── colour verification against the real Gelato catalog ────────────────────

def test_add_rejects_colour_gelato_cannot_make(tmp_path, monkeypatch):
    # REGRESSION: "make sure gelato have this color in the catalog" - a base
    # image may only be registered for a colour backed by a real approved
    # print-partner UID variant (fulfillable facets). Unknown colours and
    # unknown garments are rejected with the reason.
    from quoteforge.images import base_images as bi
    monkeypatch.setenv("BASE_IMAGES_FILE", str(tmp_path / "reg.json"))
    src = tmp_path / "x.jpg"
    Image.new("RGB", (900, 1000), (200, 20, 20)).save(src)
    res = bi.add_image(src, "m_hoodie", "NotARealColour", dest_dir=tmp_path / "b")
    assert not res.get("ok") and "colour" in res.get("reason", "").lower()
    res = bi.add_image(src, "not_a_garment", "White", dest_dir=tmp_path / "b")
    assert not res.get("ok") and "garment" in res.get("reason", "").lower()
    # a colour in the catalogue but WITHOUT real-UID backing is refused too
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    from quoteforge.etsy.fulfillability import fulfillable_apparel_facets
    g = next(x for x in APPAREL_CATALOG if x.garment_id == "m_hoodie")
    facets = fulfillable_apparel_facets(g)
    unbacked = [c for c in g.colors if facets and c not in facets[0]]
    if unbacked:   # only assertable while some catalogue colours lack UIDs
        res = bi.add_image(src, "m_hoodie", unbacked[0], dest_dir=tmp_path / "b")
        assert not res.get("ok") and "print partner" in res.get("reason", "").lower()


def test_add_rejects_bad_files_and_duplicates(tmp_path, monkeypatch):
    from quoteforge.images import base_images as bi
    monkeypatch.setenv("BASE_IMAGES_FILE", str(tmp_path / "reg.json"))
    tiny = tmp_path / "tiny.jpg"
    Image.new("RGB", (80, 80), (0, 0, 0)).save(tiny)
    res = bi.add_image(tiny, "m_hoodie", "Navy", dest_dir=tmp_path / "b")
    assert not res.get("ok") and "small" in res.get("reason", "").lower()
    notimg = tmp_path / "not.jpg"
    notimg.write_text("hello", encoding="utf-8")
    res = bi.add_image(notimg, "m_hoodie", "Navy", dest_dir=tmp_path / "b")
    assert not res.get("ok")
    good = tmp_path / "good.jpg"
    Image.new("RGB", (900, 1000), (28, 38, 74)).save(good)
    assert bi.add_image(good, "m_hoodie", "Navy", dest_dir=tmp_path / "b").get("ok")
    res = bi.add_image(good, "m_hoodie", "Navy", dest_dir=tmp_path / "b")
    assert not res.get("ok") and "force" in res.get("reason", "").lower()
    assert bi.add_image(good, "m_hoodie", "Navy", dest_dir=tmp_path / "b",
                        force=True).get("ok")


# ── the daily guards + CLI are wired ────────────────────────────────────────

def test_infra_check_invariants_registered_and_green(monkeypatch):
    # REGRESSION: the registry integrity + build parity guards run in the daily
    # sweep and are green on the real repo state.
    _real_registry(monkeypatch)
    from quoteforge.automation.infra_check import check_infrastructure
    checks = {c["name"]: c for c in check_infrastructure()["checks"]}
    assert "base_image_registry_integrity" in checks
    assert "base_image_build_parity" in checks
    assert checks["base_image_registry_integrity"]["ok"], \
        checks["base_image_registry_integrity"]
    assert checks["base_image_build_parity"]["ok"], \
        checks["base_image_build_parity"]


def test_admin_cli_registered():
    from quoteforge.admin import COMMANDS
    assert "base-images" in COMMANDS
