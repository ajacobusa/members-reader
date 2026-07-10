"""Base images - the named, owner-updatable registry of REAL product photos.

A *base image* is the real photographed product a colour composites on in the
editor/spin/tiles. The registry (``config/base_images.json``, overridable via
``BASE_IMAGES_FILE`` for tests) is the single source of truth: which garment
was photographed, in which colour, front or back, and where the file lives.
The storefront build reads it to (a) emit the side-photo colour metadata the
editor's colour match uses and (b) populate the per-colour photo map
(``APPAREL_COLOR_IMG``) so every registered colour shows its real product.

Doctrine: NO fabrication - the only accepted photo source is a file the owner
supplies (print-partner dashboard export). A colour may only be registered when
the print partner can actually make it (a real approved UID variant backs it),
so we never show a photo for an unfulfillable colour. Everything is defensive:
a missing/corrupt registry is an empty one, never a crash.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

logger = logging.getLogger("quoteforge")

_MIN_PX = 600          # smallest usable compositing base (matches intake bar)
_SIDES = ("front", "back")


def _repo_root() -> Path:
    """The repository root (this file lives at <root>/quoteforge/images/)."""
    return Path(__file__).resolve().parents[2]


def registry_path() -> Path:
    """``config/base_images.json``; overridable via BASE_IMAGES_FILE (tests)."""
    p = os.getenv("BASE_IMAGES_FILE", "").strip()
    if p:
        return Path(p)
    return _repo_root() / "config" / "base_images.json"


def load_registry() -> dict:
    """The registry, or a safe empty one when missing/corrupt (never raises)."""
    try:
        data = json.loads(registry_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("images"), list):
            return data
    except Exception as exc:  # noqa: BLE001 - missing/corrupt -> empty default
        logger.debug("base_images registry unreadable: %s", exc)
    return {"version": 1, "images": []}


def _save_registry(reg: dict) -> None:
    """Persist the registry (pretty-printed so the owner can read/edit it)."""
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")


def resolve_file(entry: dict) -> Path:
    """An entry's photo path (registry stores repo-root-relative or absolute)."""
    f = Path(str(entry.get("file") or ""))
    return f if f.is_absolute() else _repo_root() / f


def color_slug(color: str) -> str:
    """Filename-safe colour slug ('Heather Grey' -> 'heather-grey')."""
    return str(color).lower().replace(" ", "-").replace("/", "-")


def photo_color(garment_id: str, side: str = "front") -> str:
    """The colour the garment was ACTUALLY photographed in ('' = unregistered or
    no single honest colour, e.g. a two-tone raglan - never colour-match those)."""
    try:
        for e in load_registry()["images"]:
            if (e.get("garment_id") == garment_id and e.get("side") == side
                    and not e.get("percolor")):
                return str(e.get("color") or "")
    except Exception as exc:  # noqa: BLE001
        logger.debug("photo_color(%s): %s", garment_id, exc)
    return ""


def percolor_front_files() -> dict:
    """{garment_id: {colour: Path}} for registered PER-COLOUR front photos that
    exist on disk - the local (dashboard-export) source of APPAREL_COLOR_IMG."""
    out: dict = {}
    try:
        for e in load_registry()["images"]:
            if not e.get("percolor") or e.get("side") != "front":
                continue
            gid, col = str(e.get("garment_id") or ""), str(e.get("color") or "")
            p = resolve_file(e)
            if gid and col and p.exists():
                out.setdefault(gid, {})[col] = p
    except Exception as exc:  # noqa: BLE001
        logger.debug("percolor_front_files: %s", exc)
    return out


def _garment(garment_id: str):
    """The catalogue garment for garment_id, or None when unknown."""
    from quoteforge.etsy.apparel_catalog import APPAREL_CATALOG
    return next((g for g in APPAREL_CATALOG if g.garment_id == garment_id), None)


def gelato_real_colors(garment_id: str) -> list:
    """The garment's colours backed by a real approved print-partner UID variant
    (fulfillable facets - the same ground truth that filters the swatches).
    Empty list = the garment has zero fulfillable colours."""
    g = _garment(garment_id)
    if g is None:
        return []
    try:
        from quoteforge.etsy.fulfillability import fulfillable_apparel_facets
        facets = fulfillable_apparel_facets(g)
        return list(facets[0]) if facets else []
    except Exception as exc:  # noqa: BLE001
        logger.debug("gelato_real_colors(%s): %s", garment_id, exc)
        return []


def _validate_photo(src: Path) -> str:
    """'' when src is a usable photo, else the rejection reason."""
    try:
        from PIL import Image
        with Image.open(src) as im:
            im.verify()
        with Image.open(src) as im:
            w, h = im.size
        if min(w, h) < _MIN_PX:
            return (f"image too small ({w}x{h}); need >= {_MIN_PX}px on the "
                    f"short side to composite cleanly")
        return ""
    except Exception as exc:  # noqa: BLE001
        return f"not a readable image: {exc}"


def add_image(src: Path, garment_id: str, color: str, *, back: bool = False,
              force: bool = False, dest_dir: Path | None = None) -> dict:
    """Install + register an owner-supplied per-colour base image.

    Validates (real garment, colour in the catalogue AND print-partner-real,
    decodable photo, min size, no silent duplicate), copies the file to
    ``base-<garment_id>-<colour-slug>[-back].<ext>`` and appends the registry
    entry. Returns {ok: True, file, entry} or {ok: False, reason}."""
    src = Path(src)
    if not src.exists():
        return {"ok": False, "reason": f"file not found: {src}"}
    g = _garment(garment_id)
    if g is None:
        return {"ok": False, "reason": f"unknown garment '{garment_id}' "
                                       f"(see apparel_catalog garment_ids)"}
    if color not in g.colors:
        return {"ok": False, "reason": f"'{color}' is not a catalogue colour "
                                       f"for {garment_id}"}
    real = gelato_real_colors(garment_id)
    if color not in real:
        return {"ok": False, "reason":
                f"the print partner has no approved variant for {garment_id} in "
                f"'{color}' - not sellable, so a photo for it would mislead"}
    reason = _validate_photo(src)
    if reason:
        return {"ok": False, "reason": reason}
    side = "back" if back else "front"
    reg = load_registry()
    dup = [e for e in reg["images"]
           if e.get("garment_id") == garment_id and e.get("color") == color
           and e.get("side") == side and e.get("percolor")]
    if dup and not force:
        return {"ok": False, "reason": f"a {side} base image for {garment_id} "
                                       f"'{color}' already exists (pass force=True "
                                       f"/ --force to replace)"}
    dest_root = Path(dest_dir) if dest_dir else _repo_root() / "brand"
    dest_root.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower().lstrip(".") or "jpg"
    fname = f"base-{garment_id}-{color_slug(color)}"
    if back:
        fname += "-back"
    dest = dest_root / f"{fname}.{ext}"
    dest.write_bytes(src.read_bytes())
    try:
        rel = str(dest.relative_to(_repo_root()))
    except ValueError:
        rel = str(dest)
    entry = {"garment_id": garment_id, "color": color, "side": side,
             "file": rel.replace("\\", "/"), "source": "dashboard_export",
             "percolor": True, "added": date.today().isoformat()}
    reg["images"] = [e for e in reg["images"] if e not in dup] + [entry]
    _save_registry(reg)
    return {"ok": True, "file": str(dest), "entry": entry}


def validate_registry() -> list:
    """[(entry, reason)] for every bad registry entry ('' problems only) -
    the daily-guard workhorse: file missing/undecodable, colour not in the
    garment's catalogue, or (for per-colour entries) not print-partner-real."""
    bad: list = []
    for e in load_registry()["images"]:
        gid = str(e.get("garment_id") or "")
        g = _garment(gid)
        if g is None:
            bad.append((e, f"unknown garment '{gid}'"))
            continue
        if e.get("side") not in _SIDES:
            bad.append((e, f"bad side {e.get('side')!r}"))
            continue
        p = resolve_file(e)
        if not p.exists():
            bad.append((e, f"file missing: {e.get('file')}"))
            continue
        col = str(e.get("color") or "")
        if col and col not in g.colors:
            bad.append((e, f"'{col}' is not a catalogue colour for {gid}"))
            continue
        if e.get("percolor"):
            if not col:
                bad.append((e, "per-colour entry with no colour"))
            elif col not in gelato_real_colors(gid):
                bad.append((e, f"print partner has no approved '{col}' variant "
                               f"for {gid}"))
    return bad
