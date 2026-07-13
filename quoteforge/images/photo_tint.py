"""Simulated colour photos - tint ONLY the garment pixels of a real product
photo (owner-approved 'Option A', 2026-07-12).

The shop owns one real photograph per garment (a white/neutral blank on a
model). To keep the photographic preview when the buyer clicks ANY colour,
this module multiplies the target colour over the garment pixels only -
fabric folds and shadows survive (luminance is preserved), while skin, hair,
jeans and the studio background are protected by the mask.

Doctrine: these are on-screen previews, never product photography. Every
generated file registers with source='simulated_tint' (audits and the daily
guard can tell them apart), only print-partner-REAL colours are generated,
and a real dashboard export for the same colour REPLACES the simulation.
"""
from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

logger = logging.getLogger("quoteforge")

# Garment-pixel heuristics for a WHITE blank: bright and nearly colourless.
_MIN_LIGHT = 110          # max(R,G,B) above this = candidate
_MAX_SAT = 0.16           # (max-min)/max below this = nearly colourless
_BG_LIGHT = 246           # border-connected pixels this bright = studio backdrop
_BG_SAT = 0.04
_BG_ERODE = 2             # break thin blown-fabric bridges before flooding
_MIN_BLOB = 0.01          # drop colourless blobs under 1% of the frame (teeth, eyes)


def _hex_rgb(hx: str) -> tuple:
    """'#26324a' -> (38, 50, 74)."""
    h = hx.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _components(mask):
    """Label 4-connected components of a boolean mask (pure numpy + BFS - no
    scipy dependency). Returns (labels array, [component sizes])."""
    import numpy as np
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    sizes = [0]
    nxt = 0
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or labels[sy, sx]:
                continue
            nxt += 1
            q = deque([(sy, sx)])
            labels[sy, sx] = nxt
            n = 0
            while q:
                y, x = q.popleft()
                n += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not labels[yy, xx]:
                        labels[yy, xx] = nxt
                        q.append((yy, xx))
            sizes.append(n)
    return labels, sizes


def _erode(mask, n):
    """n-step 4-neighbour erosion via numpy shifts (no scipy)."""
    import numpy as np
    out = mask.copy()
    for _ in range(n):
        p = np.pad(out, 1, constant_values=False)
        out = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return out


def _fill_holes(mask):
    """True for mask plus any region NOT reachable from the border through
    ~mask (interior holes: blown-white or deep-shadow pockets inside fabric)."""
    import numpy as np
    inv = ~mask
    reach = np.zeros_like(mask)
    h, w = mask.shape
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if inv[y, x] and not reach[y, x]:
                reach[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if inv[y, x] and not reach[y, x]:
                reach[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and inv[yy, xx] and not reach[yy, xx]:
                reach[yy, xx] = True
                q.append((yy, xx))
    return mask | (inv & ~reach)


def garment_mask(arr):
    """Boolean mask of the photographed GARMENT: bright low-saturation pixels,
    minus the border-connected studio backdrop (eroded seed so blown-white
    fabric can't bridge the flood into the garment), plus interior holes
    (blown highlights / deep shadow pockets), minus tiny colourless specks
    (teeth/eye highlights) - only substantial fabric blobs survive."""
    import numpy as np
    a = arr.astype(np.int32)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0.0)
    whiteish = (mx >= _MIN_LIGHT) & (sat <= _MAX_SAT)
    # backdrop = near-pure-white region touching the frame border (flood fill;
    # NO erosion here - eroding the seed strips the row next to the border and
    # strands the flood on the ring, which tinted the whole backdrop once)
    bg_seed = (mx >= _BG_LIGHT) & (sat <= _BG_SAT)
    bg = np.zeros_like(bg_seed)
    h, w = bg_seed.shape
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bg_seed[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if bg_seed[y, x] and not bg[y, x]:
                bg[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and bg_seed[yy, xx] and not bg[yy, xx]:
                bg[yy, xx] = True
                q.append((yy, xx))
    cand = whiteish & ~bg
    labels, sizes = _components(cand)
    keep = {i for i, n in enumerate(sizes) if i and n >= _MIN_BLOB * h * w}
    if not keep:
        return cand & False
    out = np.isin(labels, list(keep))
    # blown highlights inside the garment read as 'backdrop-white' but are
    # enclosed by fabric - fill them so the tint has no white holes. Restrict
    # the fill to bright pixels (a dark design area is never fabric).
    filled = _fill_holes(out)
    return out | (filled & (mx >= 200) & (sat <= 0.12))


def _subject_mask(mask_path: Path, size: tuple):
    """A cached SUBJECT-cutout alpha (person+garment vs backdrop, produced by a
    real background-removal pass and stored next to the photo) resized to the
    photo's size. Solves what pixel heuristics cannot: blown-white fabric and
    the pure-white backdrop are identical pixels; only the silhouette separates
    them."""
    import numpy as np
    from PIL import Image
    a = Image.open(mask_path).convert("L").resize(size, Image.BILINEAR)
    return np.asarray(a) >= 128


def tint_photo(src: Path, color_hex: str, dest: Path,
               mask_path: Path | None = None) -> dict:
    """Write a colour-simulated copy of ``src``: garment pixels become
    luminance x colour (multiply - shading survives), everything else is kept
    byte-for-byte. With ``mask_path`` (a subject-cutout alpha) the garment is
    subject ∧ near-white - robust against blown highlights; without it the
    pixel heuristic is used (fine for clean studio flats, weak on model shots).
    Returns {ok, garment_px} or {ok: False, reason}."""
    try:
        import numpy as np
        from PIL import Image
        arr = np.asarray(Image.open(src).convert("RGB"))
        if mask_path is not None and Path(mask_path).exists():
            # Inside the subject cutout the rules relax: low-saturation pixels
            # are white fabric even when deeply shadowed (light floor 60), but
            # WARM near-neutrals (skin/hair highlights: R leads B) and the
            # anti-aliased silhouette halo (2px erosion) are excluded.
            subj = _erode(_subject_mask(Path(mask_path),
                                        (arr.shape[1], arr.shape[0])), 2)
            a = arr.astype(np.int32)
            mx = a.max(axis=2)
            mn = a.min(axis=2)
            sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0.0)
            warm = a[:, :, 0] > a[:, :, 2] + 10
            cand = subj & (mx >= 60) & (sat <= 0.20) & ~warm
            labels, sizes = _components(cand)
            keep = {i for i, n in enumerate(sizes)
                    if i and n >= _MIN_BLOB * cand.shape[0] * cand.shape[1]}
            mask = np.isin(labels, list(keep)) if keep else cand & False
        else:
            mask = garment_mask(arr)
        n = int(mask.sum())
        if n < 500:
            return {"ok": False, "reason": f"garment mask too small ({n}px) - "
                                           f"not a white-blank photo?"}
        rgb = np.array(_hex_rgb(color_hex), dtype=np.float64)
        lum = arr.astype(np.float64).mean(axis=2, keepdims=True) / 255.0
        # Normalise fabric luminance so a NON-white base (the heather-grey tee)
        # tints as if it were the white blank: median garment lum -> 0.88. A
        # white base is a ~no-op (its median is already ~0.88).
        med = float(np.median(lum[mask])) or 1.0
        gain = min(0.88 / med, 1.8)
        out = arr.astype(np.float64).copy()
        out[mask] = ((lum[mask] * gain).clip(0, 1.0) * rgb).clip(0, 255)
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(out.astype("uint8")).save(dest, quality=92)
        return {"ok": True, "garment_px": n, "file": str(dest)}
    except Exception as exc:  # noqa: BLE001 - a bad photo never crashes the CLI
        logger.warning("tint_photo(%s, %s) failed: %s", src, color_hex, exc)
        return {"ok": False, "reason": str(exc)}


# Colour hexes: the same customer-facing swatch values the storefront paints
# (mirrors listing_preview's client map - keep in lock-step).
COLOR_HEX = {
    "White": "#f4f3ef", "Sand": "#d8c9a8", "Heather Grey": "#b9bdc2",
    "Light Blue": "#a7c7e7", "Black": "#1c1c1e", "Charcoal": "#3a3f43",
    "Navy": "#26324a", "Royal Blue": "#2f4ba0", "Red": "#b3322c",
    "Maroon": "#5e2a32", "Forest Green": "#2e4a39", "Sage": "#7f9b78",
    "Mustard": "#cda434", "Purple": "#5b4b8a", "Dusty Rose": "#c98a9a",
    "Brown": "#5a4334",
}


def simulate_garment(garment_id: str, *, colors: list | None = None,
                     dest_dir: Path | None = None,
                     mask_path: Path | None = None) -> dict:
    """Generate + register simulated per-colour base images for one garment:
    every print-partner-REAL colour (except the photographed one) gets a tinted
    copy of the garment's real photo, registered percolor with
    source='simulated_tint'. A colour that already has a per-colour entry from
    a real export is left alone. Returns {generated, skipped, failed}."""
    from quoteforge.images import base_images as bi
    reg = bi.load_registry()
    base = next((e for e in reg["images"]
                 if e.get("garment_id") == garment_id and e.get("side") == "front"
                 and not e.get("percolor")), None)
    if base is None:
        return {"generated": [], "skipped": [], "failed": [],
                "reason": f"no base photo registered for {garment_id}"}
    src = bi.resolve_file(base)
    photo_col = str(base.get("color") or "")
    have = bi.percolor_front_files().get(garment_id, {})
    real = bi.gelato_real_colors(garment_id)
    todo = [c for c in (colors or real)
            if c in real and c != photo_col and c not in have and c in COLOR_HEX
            # a textured non-white base (the heather-grey tee) cannot fake a
            # CLEAN white garment - the heather flecks survive as marble; skip
            and not (c == "White" and photo_col != "White")]
    out = {"generated": [], "skipped": [c for c in (colors or real) if c not in todo],
           "failed": []}
    droot = Path(dest_dir) if dest_dir else bi._repo_root() / "brand"
    # subject-cutout alpha, produced once per photo (assisted background
    # removal) and cached as brand/mask-<gid>.png. REQUIRED: the pixel
    # heuristic alone cannot separate blown-white fabric from the backdrop,
    # so simulating without a real mask ships broken previews.
    mp = Path(mask_path) if mask_path else bi._repo_root() / "brand" / f"mask-{garment_id}.png"
    if todo and not mp.exists():
        return {"generated": [], "skipped": [], "failed": [],
                "reason": f"no subject mask ({mp.name}) - run the assisted "
                          f"background-removal step first"}
    from datetime import date
    for col in todo:
        dest = droot / f"sim-{garment_id}-{bi.color_slug(col)}.jpg"
        r = tint_photo(src, COLOR_HEX[col], dest, mask_path=mp)
        if not r.get("ok"):
            out["failed"].append((col, r.get("reason")))
            continue
        try:
            rel = str(dest.relative_to(bi._repo_root()))
        except ValueError:
            rel = str(dest)
        entry = {"garment_id": garment_id, "color": col, "side": "front",
                 "file": rel.replace("\\", "/"), "source": "simulated_tint",
                 "percolor": True, "added": date.today().isoformat()}
        reg = bi.load_registry()
        reg["images"] = [e for e in reg["images"]
                         if not (e.get("garment_id") == garment_id
                                 and e.get("color") == col
                                 and e.get("side") == "front"
                                 and e.get("source") == "simulated_tint")] + [entry]
        bi._save_registry(reg)
        out["generated"].append(col)
    return out
