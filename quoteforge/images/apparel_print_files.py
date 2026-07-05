"""Faithful apparel print files (#167, phase-2 backend).

The storefront exports one print file per designed side - the customer's own approved
canvas rendered as DESIGN-ONLY (text + photo at the approved placement) on a TRANSPARENT
background at the garment's print dimensions. Because it's the same canvas the buyer
approved, it is pixel-faithful to the proof (no server-side re-render, so no drift).

This module hosts each of those files to a public URL Gelato can fetch and shapes them
into the (front_url, extra_files) pair the router + gelato_api already understand:
  - the FRONT file becomes the main artwork_url (Gelato 'default' placement),
  - back / sleeve-left / sleeve-right become `extra_files` placements.

It is DORMANT until the frontend supplies `print_files`, and even then an apparel order
stays held for manual until APPAREL_PRINT_CALIBRATED=true (the router's #167 gate), so a
mis-calibrated placement can never auto-print on a real garment.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Storefront side name -> Gelato placement. FRONT is the main ('default') file; these
# three are the EXTRA placements carried in extra_files. Any other key is ignored (never
# guessed) so a stray side can't silently become a wrong placement.
EXTRA_AREAS = ("back", "sleeve-left", "sleeve-right")


def build_apparel_print_files(print_files: dict, *, has_sleeves: bool = True) -> dict:
    """Host each supplied per-side print file and shape the result.

    ``print_files``: ``{side: local_path}`` with side in
    ``{front, back, sleeve-left, sleeve-right}``.

    Returns ``{front_url, extra_files:{area:url}, hosted:[...], all_public:bool}``:
      - ``front_url`` - public URL for the front file (``""`` if none/unhostable, in
        which case the caller keeps its existing artwork).
      - ``extra_files`` - ``{area: url}`` for back/sleeve placements only.
      - ``hosted`` - the sides successfully hosted.
      - ``all_public`` - False if any file fell back to a non-public (local) URL; the
        router's public-URL guard then holds the order for manual rather than handing
        Gelato a URL it can't fetch.

    A side whose file is missing or unhostable is SKIPPED, never guessed.
    """
    from quoteforge.automation.file_host import publish_print_file

    front_url = ""
    extra_files: dict = {}
    hosted: list = []
    all_public = True
    for side, path in (print_files or {}).items():
        if not path:
            continue
        # Defense-in-depth (L-1): a sleeveless garment (tank) can NEVER host a sleeve
        # print file, even if a caller passes one - you can't print a sleeve that doesn't
        # exist. The frontend already gates this; this is the backend backstop.
        if not has_sleeves and side in ("sleeve-left", "sleeve-right"):
            logger.debug("apparel print file: dropping %r on a sleeveless garment", side)
            continue
        res = publish_print_file(path)
        url = res.get("url") or ""
        if not url:
            continue
        if not res.get("public"):
            all_public = False          # local:// fallback -> router holds for manual
        if side == "front":
            front_url = url
        elif side in EXTRA_AREAS:
            extra_files[side] = url
        else:
            logger.debug("apparel print file: ignoring unknown side %r", side)
            continue
        hosted.append(side)
    return {"front_url": front_url, "extra_files": extra_files,
            "hosted": hosted, "all_public": all_public}
