"""Artwork preflight checker — the print-quality gate before Gelato.

A technically successful order can still print BADLY (wrong size, low resolution,
wrong colour mode, text crammed to the edge). This validates the finished file
against the ordered product's print spec and BLOCKS the order if it would print
poorly, so the failure is caught before money is spent on a bad print.

Checks: file type, colour mode, pixel dimensions vs. the product's 300-DPI spec,
effective DPI, aspect-ratio match, non-empty/not-corrupt, and a non-blocking
opacity warning (transparent areas print with the background showing through).
Returns a pass/fail report with a reason per check.
"""
from pathlib import Path

from quoteforge.config import (
    PREFLIGHT_TARGET_DPI, PREFLIGHT_MIN_DPI, PREFLIGHT_DIMENSION_TOLERANCE,
    PREFLIGHT_ASPECT_TOLERANCE,
)
from quoteforge.etsy.gelato_catalog import get_product, dimensions_for

_ALLOWED_FORMATS = {"PNG", "JPEG", "JPG", "TIFF"}
# Gelato accepts RGB and converts to CMYK; palette/grayscale/CMYK-in-RGB-file are
# the real risks for unexpected colour shifts.
_ALLOWED_MODES = {"RGB", "RGBA"}


def _check(name: str, ok: bool, detail: str) -> dict:
    """Build a single named pass/fail check entry."""
    return {"name": name, "ok": ok, "detail": detail}


def run_preflight(image_path, product_identifier: str = "") -> dict:
    """Validate an artwork file for print. Returns {ok, checks, blocking}."""
    from PIL import Image
    path = Path(image_path)
    checks: list[dict] = []

    if not path.exists():
        return {"ok": False, "blocking": True,
                "checks": [_check("file exists", False, f"missing: {path}")]}

    # File type by extension + actual decode.
    try:
        with Image.open(path) as im:
            im_format = (im.format or "").upper()
            mode = im.mode
            width, height = im.size
            dpi = im.info.get("dpi", (0, 0))
            # Any non-opaque pixel? (alpha min < 255). Only meaningful for RGBA.
            alpha_min = im.getchannel("A").getextrema()[0] if mode == "RGBA" else 255
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "blocking": True,
                "checks": [_check("readable image", False,
                                  f"cannot open: {type(exc).__name__}")]}

    checks.append(_check("file type", im_format in _ALLOWED_FORMATS,
                         f"{im_format or 'unknown'} "
                         f"({'allowed' if im_format in _ALLOWED_FORMATS else 'use PNG/JPG'})"))
    checks.append(_check("colour mode", mode in _ALLOWED_MODES,
                         f"{mode} ({'ok' if mode in _ALLOWED_MODES else 'convert to RGB'})"))

    # Opacity (NON-blocking): Gelato flattens transparency, so unintended
    # transparent areas print with the background showing through. Warn, don't block.
    if mode == "RGBA":
        checks.append(_check("opacity", alpha_min == 255,
                             "fully opaque" if alpha_min == 255 else
                             "has transparent areas - will print with background "
                             "showing through"))

    # Non-empty / not effectively blank.
    file_kb = path.stat().st_size / 1024
    checks.append(_check("not empty", file_kb > 5, f"{file_kb:.0f} KB"))

    # Required print dimensions for the ordered product (300 DPI spec).
    req_w, req_h = dimensions_for(product_identifier)
    product = get_product(product_identifier)
    size_label = product.size if product else "18x24 in (default)"

    # Allow either orientation (portrait/landscape) match.
    def _fits(w, h, rw, rh):
        """True if the image meets the required pixel size in either orientation."""
        tol = PREFLIGHT_DIMENSION_TOLERANCE
        return (w >= rw * (1 - tol) and h >= rh * (1 - tol)) or \
               (w >= rh * (1 - tol) and h >= rw * (1 - tol))

    dims_ok = _fits(width, height, req_w, req_h)
    checks.append(_check("resolution", dims_ok,
                         f"{width}x{height}px vs required ~{req_w}x{req_h}px "
                         f"for {size_label}"))

    # Effective DPI for the physical size (pixels / inches).
    if product and product.size:
        try:
            in_w, in_h = (float(x) for x in
                          product.size.replace(" in", "").lower().split("x"))
            eff_dpi = min(width / max(in_w, 0.1), height / max(in_h, 0.1))
        except Exception:  # noqa: BLE001
            eff_dpi = max(dpi[0] if dpi else 0, 0)
    else:
        eff_dpi = dpi[0] if dpi else 0
    checks.append(_check("effective DPI", eff_dpi >= PREFLIGHT_MIN_DPI,
                         f"{eff_dpi:.0f} DPI (target {PREFLIGHT_TARGET_DPI}, "
                         f"min {PREFLIGHT_MIN_DPI})"))

    # Aspect ratio match (catches a wrong-size render -> would crop/letterbox).
    got_ar = max(width, height) / max(min(width, height), 1)
    req_ar = max(req_w, req_h) / max(min(req_w, req_h), 1)
    ar_ok = abs(got_ar - req_ar) <= PREFLIGHT_ASPECT_TOLERANCE
    checks.append(_check("aspect ratio", ar_ok,
                         f"{got_ar:.2f} vs product {req_ar:.2f}"))

    blocking = any(not c["ok"] for c in checks
                   if c["name"] in ("file type", "colour mode", "not empty",
                                    "resolution", "effective DPI", "aspect ratio"))
    return {"ok": not blocking, "blocking": blocking, "checks": checks,
            "product": size_label}


def format_preflight_text(report: dict) -> str:
    """Render the preflight report as a human-readable pass/fail checklist."""
    head = "ARTWORK PREFLIGHT - " + ("PASS" if report["ok"] else "FAIL (blocking)")
    lines = ["=" * 56, head, "=" * 56]
    for c in report["checks"]:
        lines.append(f"  [{'OK' if c['ok'] else 'XX'}] {c['name']}: {c['detail']}")
    lines.append("=" * 56)
    return "\n".join(lines)
