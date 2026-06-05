"""Customer photo quality gate + automated 'please resend' reply.

When a buyer supplies their OWN photo, it must be high enough resolution to print
well at the ordered size — a 600x800 phone screenshot will look terrible on an
18x24 poster. This checks the photo against the print spec and, if it fails,
produces a polite, specific auto-reply asking for a better one (with the exact
pixels needed). Bad photos never reach print.
"""
from pathlib import Path

from quoteforge.config import CUSTOMER_PHOTO_MIN_DPI
from quoteforge.etsy.gelato_catalog import get_product, dimensions_for

_ALLOWED_MODES = {"RGB", "RGBA", "L"}
_ALLOWED_FORMATS = {"JPEG", "JPG", "PNG", "TIFF", "HEIF", "HEIC", "WEBP"}


def check_customer_photo(image_path, product_size: str = "",
                         min_dpi: int = None) -> dict:
    """Validate a buyer-supplied photo for print at the ordered size."""
    from PIL import Image
    min_dpi = CUSTOMER_PHOTO_MIN_DPI if min_dpi is None else min_dpi
    path = Path(image_path)
    if not path.exists():
        return {"ok": False, "reason": "file not found", "needs_resend": True,
                "actual_px": (0, 0), "effective_dpi": 0, "min_dpi": min_dpi}
    try:
        with Image.open(path) as im:
            fmt = (im.format or "").upper()
            mode = im.mode
            w, h = im.size
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"unreadable image ({type(exc).__name__})",
                "needs_resend": True, "actual_px": (0, 0),
                "effective_dpi": 0, "min_dpi": min_dpi}

    # Required print inches for the ordered product (default 18x24).
    product = get_product(product_size)
    if product and product.size:
        try:
            in_w, in_h = (float(x) for x in
                          product.size.replace(" in", "").lower().split("x"))
        except Exception:  # noqa: BLE001
            in_w, in_h = 18.0, 24.0
        size_label = product.size
    else:
        in_w, in_h = 18.0, 24.0
        size_label = "18x24 in (default)"

    # Effective DPI = photo pixels spread across the print inches (best fit, so
    # orientation doesn't matter).
    eff_dpi = min(max(w, h) / max(in_w, in_h), min(w, h) / min(in_w, in_h))
    required_w, required_h = dimensions_for(product_size)

    problems = []
    if fmt and fmt not in _ALLOWED_FORMATS:
        problems.append(f"format {fmt} (use JPG/PNG)")
    if mode not in _ALLOWED_MODES:
        problems.append(f"colour mode {mode}")
    if eff_dpi < min_dpi:
        problems.append(f"too low resolution ({eff_dpi:.0f} DPI, need >= {min_dpi})")

    ok = not problems
    return {
        "ok": ok, "needs_resend": not ok,
        "reason": "; ".join(problems) if problems else "photo OK",
        "actual_px": (w, h), "effective_dpi": round(eff_dpi),
        "min_dpi": min_dpi, "size_label": size_label,
        "required_px": (required_w, required_h),
    }


def photo_request_message(check: dict, customer_name: str = "there",
                          recipient: str = "your order") -> str:
    """The polite auto-reply asking the buyer for a print-quality photo."""
    aw, ah = check["actual_px"]
    rw, rh = check["required_px"]
    return (
        f"Hi {customer_name}! Thank you for your order and for sending your photo "
        f"for {recipient}.\n\n"
        f"I want your print to look absolutely beautiful, and unfortunately the "
        f"photo you sent is a little too low-resolution to print crisply at this "
        f"size (it's {aw}x{ah} pixels, and for a sharp {check['size_label']} "
        f"print I'd need around {rw}x{rh} pixels).\n\n"
        f"Could you send the ORIGINAL, full-size version? A few tips that help:\n"
        f"  - Send the original photo file, not a screenshot or a copy from "
        f"social media (those are compressed).\n"
        f"  - On a phone, choose 'Actual Size' / 'Large' when sharing.\n"
        f"  - Email or message the file directly rather than pasting it.\n\n"
        f"As soon as I have a higher-resolution version I'll create your proof "
        f"right away. Thank you so much - I can't wait to make this special for you!"
    )
