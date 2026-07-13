"""Simulated colour photos (owner-approved Option A): tint ONLY the garment
pixels of the real white product photo per approved colour, so every colour
click keeps the photographic model preview - consistency the UX demanded.

Doctrine guardrails pinned here: skin/hair/background are never tinted, only
print-partner-REAL colours are generated, every generated entry is marked
source='simulated_tint' in the registry (a real dashboard export replaces it),
and the editor labels the simulated state as a digital preview.
"""
import json

import numpy as np
from PIL import Image


def _fake_photo(tmp_path):
    """Synthetic 'model photo': white bg, neutral-white garment blob with
    shading, a saturated skin patch and blue jeans."""
    a = np.full((200, 160, 3), 255, dtype=np.uint8)          # white background
    a[40:150, 40:120] = (232, 231, 228)                       # garment (light, low sat)
    a[60:100, 60:100] = (214, 212, 208)                       # garment shading
    a[10:38, 70:90] = (224, 172, 138)                          # skin (saturated)
    a[150:195, 55:105] = (70, 90, 140)                         # jeans (blue)
    p = tmp_path / "photo.jpg"
    Image.fromarray(a).save(p, quality=95)
    return p


def test_tint_recolours_garment_only(tmp_path):
    # REGRESSION: navy tint lands on the garment blob (dark, blue-leaning) while
    # skin, jeans and the white background stay untouched - never navy teeth.
    from quoteforge.images.photo_tint import tint_photo
    src = _fake_photo(tmp_path)
    dst = tmp_path / "navy.jpg"
    r = tint_photo(src, "#26324a", dst)
    assert r.get("ok"), r
    out = np.asarray(Image.open(dst).convert("RGB")).astype(int)
    g = out[80, 80]                                            # garment centre
    assert g[2] > g[0] and g.max() < 140, g                    # navy-ish + dark
    assert out[20, 80][0] > 180 and out[20, 80][0] > out[20, 80][2], out[20, 80]  # skin kept warm
    assert abs(int(out[170, 80][2]) - 140) < 30, out[170, 80]  # jeans untouched
    assert out[5, 5].min() > 235, out[5, 5]                    # background stays white


def test_tint_preserves_fabric_shading(tmp_path):
    # REGRESSION: the shaded garment region stays DARKER than the lit region
    # after tinting - multiply keeps folds visible, no flat colour block.
    from quoteforge.images.photo_tint import tint_photo
    src = _fake_photo(tmp_path)
    dst = tmp_path / "red.jpg"
    assert tint_photo(src, "#b3322c", dst).get("ok")
    out = np.asarray(Image.open(dst).convert("RGB")).astype(int)
    lit, shaded = out[45, 45].sum(), out[80, 80].sum()
    assert shaded < lit, (shaded, lit)


def test_simulate_registers_only_real_colours_with_sim_source(tmp_path, monkeypatch):
    # REGRESSION: simulate generates + registers ONLY print-partner-real colours
    # (never an unfulfillable shade) and marks every entry simulated_tint so a
    # real dashboard export later replaces it and audits can tell them apart.
    from quoteforge.images import base_images as bi
    from quoteforge.images.photo_tint import simulate_garment
    monkeypatch.setenv("BASE_IMAGES_FILE", str(tmp_path / "reg.json"))
    src = _fake_photo(tmp_path)
    (tmp_path / "reg.json").write_text(json.dumps({"version": 1, "images": [
        {"garment_id": "m_hoodie", "color": "White", "side": "front",
         "file": str(src), "source": "dashboard_export", "added": "2026-07-12"},
        {"garment_id": "m_tshirt", "color": "White", "side": "front",
         "file": str(src), "source": "dashboard_export", "added": "2026-07-12"}]}),
        encoding="utf-8")
    full = Image.new("L", (160, 200), 255)             # trivial all-subject mask
    full.save(tmp_path / "mask.png")
    r = simulate_garment("m_hoodie", dest_dir=tmp_path / "sim",
                         mask_path=tmp_path / "mask.png")
    assert r["generated"], r
    # and WITHOUT a subject mask, simulate refuses while work is pending
    # (heuristics ship broken previews) - m_tshirt has a base but no sims yet
    r2 = simulate_garment("m_tshirt", dest_dir=tmp_path / "sim2",
                          mask_path=tmp_path / "nope.png")
    assert not r2["generated"] and "mask" in (r2.get("reason") or "")
    real = set(bi.gelato_real_colors("m_hoodie"))
    reg = bi.load_registry()
    sims = [e for e in reg["images"] if e.get("source") == "simulated_tint"]
    assert sims and all(e["color"] in real for e in sims)
    assert all(e.get("percolor") for e in sims)
    assert not any(e["color"] == "White" for e in sims)   # the photographed colour needs no sim
    # generated files exist and flow into the per-colour map
    pc = bi.percolor_front_files()
    assert set(pc.get("m_hoodie", {})) == {e["color"] for e in sims}


def test_editor_labels_simulated_colours(tmp_path):
    # REGRESSION: honesty label - when the shown base is a tinted simulation the
    # preview caption says so; the page carries the sim-colour map.
    from PIL import Image as _I
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    _I.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    h = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                        out_path=tmp_path / "h.html",
                        frame_picker=True).read_text(encoding="utf-8")
    assert "const APPAREL_SIM = " in h
    assert "colour shown is a digital preview" in h


def test_admin_subcommand_registered():
    from quoteforge.admin import _cmd_base_images
    import inspect
    assert "simulate" in inspect.getsource(_cmd_base_images)
