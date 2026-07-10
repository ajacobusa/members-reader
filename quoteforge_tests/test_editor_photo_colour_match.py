"""Editor real-photo colour match: the design editor showed a DRAWN cartoon
garment even though a real photographed product exists and is deployed
(assets/tile-<gid>.jpg) - because the single per-garment photo was gated on
per-colour photos existing (APPAREL_COLOR_IMG), and that map is empty off-live.

The honest middle ground: the real photo may stand in whenever the buyer's
SELECTED colour IS the colour the garment was actually photographed in (the
editor's default colour is White and most photos are white garments - so the
first-open preview looks like the real product). Any other colour keeps the
recolouring silhouette, preserving the earlier "T-shirt colour is not changing"
regression fix. Per-colour supplier photos at go-live remain the full solution.
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


def _side_img(h: str) -> dict:
    m = re.search(r"const APPAREL_SIDE_IMG = (\{.*?\});", h)
    assert m, "APPAREL_SIDE_IMG missing from the page"
    return json.loads(m.group(1))


def test_side_img_carries_verified_photo_colour(tmp_path):
    # REGRESSION: APPAREL_SIDE_IMG entries must carry the colour the garment was
    # ACTUALLY photographed in, pinned to the eyeball-verified census of the real
    # brand/tile-*.jpg photos. Getting this wrong shows a buyer who picked White
    # a grey shirt (w_tshirt was shot in Heather Grey, NOT white) - the exact
    # mislabeled-photo class the fulfillability audits exist to catch. Raglans are
    # two-tone (white body / grey sleeves): no single colour name is honest, so
    # they carry '' and never photo-match.
    d = _side_img(_page(tmp_path))
    census = {
        "m_tshirt": "White", "w_tshirt": "Heather Grey",
        "m_tank": "White", "w_tank": "White",
        "m_longsleeve": "White", "w_longsleeve": "White",
        "m_raglan": "", "w_raglan": "",
        "m_polo": "White",
        "m_hoodie": "White", "w_hoodie": "White",
        "m_sweatshirt": "White", "w_sweatshirt": "White",
    }
    for gid, colour in census.items():
        if gid in d:                       # only photographed garments get entries
            assert d[gid].get("color") == colour, (
                f"{gid}: photo colour must be {colour!r}, got {d[gid].get('color')!r}")
    # the default-colour garment of the reported screenshot must be photo-matched
    assert d.get("m_hoodie", {}).get("color") == "White"


def test_editor_photo_stands_in_when_colour_matches(tmp_path):
    # REGRESSION: with APPAREL_COLOR_IMG empty (off-live) the editor drew a cartoon
    # hoodie although a real white product photo was deployed and White was the
    # selected (default) colour. The drawArt gate must accept the side photo when
    # the selected colour equals the photo's own colour - and ONLY then, so the
    # earlier "same white tee for EVERY colour" bug stays fixed.
    h = _page(tmp_path)
    assert "_photoColorMatch" in h
    # FRONT stand-in is colour-exact; only the BACK may lean on _hasColorPhotos
    # (see test_base_images.test_front_standin_is_colour_exact for the rationale)
    assert "if(!_u && (_photoColorMatch || (_side==='back'&&_hasColorPhotos)))" in h
    # the match is derived from the emitted metadata, never guessed client-side
    assert "_sm.color===_selc" in h.replace(" ", "").replace("_sm&&", "") or \
           "_sm.color===_selc" in h
    # the colour-accurate silhouette path stays wired for non-matching colours
    assert "function drawGarment" in h and "APPARELCOLOR[cn]||" in h


def test_spin_photo_gate_matches_editor_gate(tmp_path):
    # REGRESSION: the 3D-ish spin preview (_mockBase) has the same colour-honesty
    # gate as drawArt; the two must stay in step or the editor shows a photo while
    # the spin refuses (or vice versa). It must accept the photo-colour match too.
    h = _page(tmp_path)
    assert "if(!hasColor&&!photoMatch) return null;" in h
