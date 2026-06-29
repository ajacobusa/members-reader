"""Shared AI design-assistant logic for EVERY product (apparel, mug, calendar,
branded, wall art, Pro Designer).

Two layers, so the customer always gets useful help:
  * DETERMINISTIC (no AI, no network, always on): photo_quality_review() and
    placement_suggestion() reason purely from pixel dimensions + the product's print
    aspect. Fast, free, unit-tested, and identical to the client-side editor copy.
  * AI ENRICHMENT (Claude vision, when a key is present): ai_photo_review() adds
    lighting / blur / subject-framing / crop feedback on top. TEST_MODE-safe and
    never raises - the deterministic layer is the real guarantee.

Nothing here places an order, touches pricing, or exposes a vendor name.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PRINT_DPI = 150          # the resolution below which a print starts to look soft

# Approx PRINTABLE aspect ratio (width/height) per product family, so the crop
# advice matches what actually prints. Wall art uses the chosen inch size instead.
PRODUCT_ASPECT = {
    "mug": 2.4,          # wrap-around band is wide and short
    "apparel": 0.82,     # chest print is slightly tall
    "branded": 1.0,      # totes/bottles ~ square-ish print area
    "calendar": 1.33,    # landscape photo area
    "wallart": None,     # taken from the chosen size (e.g. 18x24)
    "poster": None,
}


def _target_aspect(product_kind: str, size_label: str):
    """Width/height the print wants, from the product or the chosen inch size."""
    k = (product_kind or "wallart").lower()
    if k in PRODUCT_ASPECT and PRODUCT_ASPECT[k] is not None:
        return PRODUCT_ASPECT[k]
    parts = [p for p in (size_label or "").replace("in", "").strip().split("x")]
    try:
        w, h = float(parts[0]), float(parts[1])
        if w > 0 and h > 0:
            return w / h
    except (ValueError, IndexError) as exc:
        logger.debug("aspect parse skipped for size label: %s", exc)
    return None


def photo_quality_review(width, height, product_kind: str = "wallart",
                         size_label: str = "") -> dict:
    """Deterministic photo-quality review from pixel dimensions. No AI/network.

    Returns {score 0-100, verdict, mp, max_print_in (w,h), crop, tips[]}.
    """
    w, h = int(width or 0), int(height or 0)
    if w <= 0 or h <= 0:
        return {"score": 0, "verdict": "No image", "mp": 0,
                "max_print_in": (0, 0), "crop": "", "tips": [
                    "Upload a photo to see an instant quality review."]}
    long_, short = max(w, h), min(w, h)
    mp = round(w * h / 1_000_000, 1)
    score, tips = 100, []

    # 1) Resolution / sharpness
    if long_ < 1000:
        score -= 45
        tips.append(f"Low resolution ({w}x{h}px) - upload a larger original "
                    "so the print stays crisp.")
    elif long_ < 1600:
        score -= 18
        tips.append(f"Medium resolution ({w}x{h}px) - great for smaller prints; "
                    "a larger file is sharper at big sizes.")
    else:
        tips.append(f"Sharp resolution ({w}x{h}px, {mp} MP).")

    # 2) Largest size it prints sharp at
    max_w_in = round(long_ / PRINT_DPI, 1)
    max_h_in = round(short / PRINT_DPI, 1)

    # 3) Crop fit vs the product's print shape
    crop = ""
    target = _target_aspect(product_kind, size_label)
    if target:
        photo_ar = w / h
        ratio = photo_ar / target if target else 1
        if ratio > 1.35 or ratio < 0.74:
            score -= 12
            if photo_ar > target:
                crop = ("This photo is wider than the print area - the sides may "
                        "crop. Zoom out or nudge it to keep everyone in.")
            else:
                crop = ("This photo is taller than the print area - the top/bottom "
                        "may crop. Zoom out or nudge it to fit.")
            tips.append(crop)

    score = max(0, min(100, score))
    verdict = ("Great photo" if score >= 80
               else "Good - a couple of tips" if score >= 55
               else "Use a higher-quality photo")
    return {"score": score, "verdict": verdict, "mp": mp,
            "max_print_in": (max_w_in, max_h_in), "crop": crop, "tips": tips}


def placement_suggestion(photo_w, photo_h, n_text_lines: int = 0,
                         product_kind: str = "wallart") -> dict:
    """Deterministic 'auto-arrange' suggestion: a layout + where text and the photo
    should sit so they do not overlap. Returns
    {layout, text_pos {x,y}, photo_focal {x,y}, rationale}.
    """
    pw, ph = int(photo_w or 0), int(photo_h or 0)
    has_photo = pw > 0 and ph > 0
    portrait = has_photo and ph > pw * 1.1
    landscape = has_photo and pw > ph * 1.1

    if not has_photo:
        return {"layout": "freeform", "text_pos": {"x": 0.5, "y": 0.5},
                "photo_focal": {"x": 0.5, "y": 0.5},
                "rationale": "No photo yet - centered wording."}

    # With a photo + wording, keep the subject centered and push text clear of it.
    if n_text_lines >= 1:
        if landscape:
            layout, ty = "banner", 0.86      # wide photo -> caption band beneath
            rationale = "Wide photo with a caption band underneath."
        elif portrait:
            layout, ty = "badge", 0.5
            rationale = "Tall photo framed by arched wording (badge)."
        else:
            layout, ty = "badge", 0.5
            rationale = "Square photo centered with arched wording."
        return {"layout": layout, "text_pos": {"x": 0.5, "y": ty},
                "photo_focal": {"x": 0.5, "y": 0.5}, "rationale": rationale}
    return {"layout": "freeform", "text_pos": {"x": 0.5, "y": 0.9},
            "photo_focal": {"x": 0.5, "y": 0.5},
            "rationale": "Photo-first - subject centered."}


def ai_photo_review(image_path, product_kind: str = "wallart",
                    size_label: str = "", width=None, height=None) -> dict:
    """Deterministic review + optional Claude-vision enrichment (lighting/blur/
    subject). Merges the AI note + tips into the deterministic result. Never raises;
    in TEST_MODE / no key it returns the deterministic review only."""
    from pathlib import Path
    p = Path(image_path) if image_path else None
    if (width is None or height is None) and p and p.exists():
        try:
            from PIL import Image
            with Image.open(p) as im:
                width, height = im.size
        except Exception:  # noqa: BLE001
            width = width or 0
            height = height or 0
    base = photo_quality_review(width or 0, height or 0, product_kind, size_label)
    try:
        from quoteforge.ai.assistant import ai_vision_check
        ai = ai_vision_check(str(p)) if p else {"ok": True, "note": ""}
    except Exception:  # noqa: BLE001
        ai = {"ok": True, "note": ""}
    base["ai_ok"] = bool(ai.get("ok", True))
    note = (ai.get("note") or "").strip()
    if note and note.upper() not in ("OK", "AI VISION SKIPPED"):
        base["tips"].append(note if ai.get("ok", True)
                            else "Heads up: " + note.replace("ISSUE:", "").strip())
        if not ai.get("ok", True):
            base["score"] = min(base["score"], 60)
            base["verdict"] = "Use a higher-quality photo"
    return base
