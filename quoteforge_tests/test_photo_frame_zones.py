"""Photo-aware print-frame zones: when the editor shows the REAL product photo,
the default wording frame must land on the photo's CHEST and the sleeve frames
on the photo's ARMS - not on the coordinates tuned for the drawn silhouette
(which put the front frame over the model's face and the sleeve frame floating
off the garment). Zones live in the base-image registry (per photographed
garment, owner-tunable) and only apply while the photo is the active base;
the drawn silhouette keeps its original defaults.
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


def test_registry_zones_present_and_sane():
    # REGRESSION: every photographed FULFILLABLE garment carries zones measured
    # against its actual photo; values are canvas fractions. The hoodie (the
    # reported screenshot) must anchor the chest at mid-garment, NOT the drawn
    # default y=0.35 that sat on the model's face.
    from quoteforge.images import base_images as bi
    z = bi.photo_zones("m_hoodie")
    assert z and "front" in z and "sleeve_left" in z and "sleeve_right" in z
    assert z["front"][1] >= 0.45, "hoodie chest anchor must sit below the face"
    for name, vals in z.items():
        assert 0.0 < vals[0] < 1.0 and 0.0 < vals[1] < 1.0, (name, vals)
        if len(vals) > 2:
            assert 0.2 <= vals[2] <= 1.5, (name, vals)
    # sleeve anchors are on opposite arms
    assert z["sleeve_left"][0] < 0.5 < z["sleeve_right"][0]
    # a sleeveless garment must NOT carry sleeve zones (no sleeve to print)
    zt = bi.photo_zones("m_tank")
    assert zt and "sleeve_left" not in zt and "sleeve_right" not in zt


def test_zones_reach_the_page_and_editor_consults_them(tmp_path):
    # REGRESSION: APPAREL_SIDE_IMG carries the zones, and BOTH default paths
    # (fresh-side front frame + the sleeve default box) consult _photoZone -
    # gated on the photo actually being the active base.
    h = _page(tmp_path)
    m = re.search(r"const APPAREL_SIDE_IMG = (\{.*?\});", h)
    d = json.loads(m.group(1))
    assert "zones" in d.get("m_hoodie", {}), "zones missing from the page map"
    assert "function _photoZone" in h
    assert "_photoZone('front')" in h            # fresh-side front default
    assert "_photoZone(p==='sleeve-left'?'sleeve_left':'sleeve_right')" in h  # sleeve default
    # the drawn-silhouette defaults survive as the fallback
    assert "x:(_l?0.13:0.87)" in h


def test_registry_validation_rejects_bad_zones(tmp_path, monkeypatch):
    # REGRESSION: a mistyped zone (x=5.0) must be a registry-integrity problem
    # the daily invariant #87 reports - not a silently off-canvas frame.
    from quoteforge.images import base_images as bi
    monkeypatch.setenv("BASE_IMAGES_FILE", str(tmp_path / "reg.json"))
    (tmp_path / "reg.json").write_text(json.dumps({"version": 1, "images": [
        {"garment_id": "m_hoodie", "color": "White", "side": "front",
         "file": "brand/tile-m_hoodie.jpg", "source": "dashboard_export",
         "added": "2026-07-11", "zones": {"front": [5.0, 0.5]}}]}),
        encoding="utf-8")
    bad = bi.validate_registry()
    assert bad and "zone" in bad[0][1].lower()
