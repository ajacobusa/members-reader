"""AI-assisted photo enhancement — rescue a too-low-res customer photo.

When a buyer's OWN photo is below the print-resolution floor, the quality gate
(`photo_check.check_customer_photo`) would bounce it back and ask for a better
one. Before doing that, we try to ENHANCE it: upscale toward the resolution the
ordered size needs, then 100%-RE-REVIEW the result through the very same gate.
Only a result that now passes is used — nothing unreviewed ever reaches print.

Two upscalers, best-available first:
  * an AI super-resolution provider when ``AI_UPSCALE_API_KEY`` is set (pluggable
    and key-gated, like every other paid integration here) — good to ~4x, and
  * a high-quality Lanczos resample as the always-on, no-dependency baseline —
    capped at 2x, beyond which upscaling adds pixels but not real detail.

The cap is the honesty guard: a photo so small it needs more than the cap to
clear the floor is NOT silently faked up to a blurry "pass" — it fails the
re-review and the buyer is still asked for a better photo. In TEST_MODE or with
no key the network is never touched (the Lanczos baseline runs locally), so the
whole path is exercised by the suite without any paid call.
"""
from __future__ import annotations

import math
from pathlib import Path

# How far each backend may upscale before the result stops being honest.
_LANCZOS_MAX_SCALE = 2.0
_AI_MAX_SCALE = 4.0


def _ai_upscale(src: Path, target_w: int, target_h: int) -> bytes | None:
    """Pluggable AI super-resolution. POSTs the source image to the configured
    provider and returns the enhanced PNG bytes, or None on any problem (so the
    caller falls back to the Lanczos baseline). Key-gated + TEST_MODE-safe:
    never calls the network without a real key."""
    from quoteforge.config import TEST_MODE
    try:
        from quoteforge.config import AI_UPSCALE_API_KEY, AI_UPSCALE_API_URL
    except Exception:  # noqa: BLE001 — config without the keys: no AI tier
        return None
    if TEST_MODE or not AI_UPSCALE_API_KEY or not AI_UPSCALE_API_URL:
        return None
    try:
        import requests
        with open(src, "rb") as fh:
            resp = requests.post(
                AI_UPSCALE_API_URL,
                headers={"Authorization": f"Bearer {AI_UPSCALE_API_KEY}"},
                files={"image": fh},
                data={"target_width": target_w, "target_height": target_h},
                timeout=60)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:  # noqa: BLE001 — any failure → Lanczos baseline
        return None
    return None


def enhance_to_print(src, product_size: str = "", out_dir=None,
                     min_dpi: int = None) -> dict:
    """Try to lift a too-low-res photo to print quality, then re-review it.

    Returns a dict:
      ok       — bool: the (re-reviewed) image is now print-quality.
      path     — Path: the image to use (enhanced on success; original otherwise).
      original — Path: the source photo.
      scale    — float: linear upscale applied (1.0 = none).
      method   — "none" | "ai" | "lanczos" | "disabled" | "error".
      review   — dict: the check_customer_photo result for `path` (100% reviewed).

    Never raises — on any failure it returns ok=False with the original photo so
    the caller falls back to asking the buyer for a better one.
    """
    from quoteforge.images.photo_check import check_customer_photo
    src = Path(src)
    review0 = check_customer_photo(src, product_size, min_dpi)

    # Already good, or a feature kill-switch / unreadable file: no enhancement.
    if review0.get("ok"):
        return {"ok": True, "path": src, "original": src, "scale": 1.0,
                "method": "none", "review": review0}
    try:
        from quoteforge.config import AI_PHOTO_ENHANCE
    except Exception:  # noqa: BLE001
        AI_PHOTO_ENHANCE = True
    if not AI_PHOTO_ENHANCE:
        return {"ok": False, "path": src, "original": src, "scale": 1.0,
                "method": "disabled", "review": review0}

    eff = review0.get("effective_dpi") or 0
    floor = review0.get("min_dpi") or 0
    # Unreadable / non-resolution failures (bad format, missing file) aren't
    # fixable by upscaling — don't try.
    if eff <= 0 or floor <= 0 or "resolution" not in review0.get("reason", ""):
        return {"ok": False, "path": src, "original": src, "scale": 1.0,
                "method": "error", "review": review0}

    try:
        from PIL import Image
        with Image.open(src) as im:
            im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
            w, h = im.size
            # Scale needed to clear the floor, with a hair of headroom so integer
            # rounding never lands a pixel under. Cap by the active backend.
            from quoteforge.config import TEST_MODE
            try:
                from quoteforge.config import AI_UPSCALE_API_KEY, AI_UPSCALE_API_URL
                ai_on = bool(AI_UPSCALE_API_KEY and AI_UPSCALE_API_URL) and not TEST_MODE
            except Exception:  # noqa: BLE001
                ai_on = False
            cap = _AI_MAX_SCALE if ai_on else _LANCZOS_MAX_SCALE
            needed = (floor / eff) * 1.02
            scale = min(cap, needed)
            target_w, target_h = math.ceil(w * scale), math.ceil(h * scale)

            out_dir = Path(out_dir) if out_dir else src.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = out_dir / "custom_photo_enhanced.png"

            method = "lanczos"
            ai_bytes = _ai_upscale(src, target_w, target_h) if ai_on else None
            if ai_bytes:
                dst.write_bytes(ai_bytes)
                method = "ai"
            else:
                im.resize((target_w, target_h), Image.LANCZOS).save(dst, "PNG")
    except Exception:  # noqa: BLE001 — never break the pipeline on enhancement
        return {"ok": False, "path": src, "original": src, "scale": 1.0,
                "method": "error", "review": review0}

    # 100% RE-REVIEW: the enhanced image goes through the exact same gate. Only a
    # genuine pass is accepted; a capped-but-still-too-small result fails here.
    review1 = check_customer_photo(dst, product_size, min_dpi)
    return {"ok": bool(review1.get("ok")), "path": dst if review1.get("ok") else src,
            "original": src, "scale": round(scale, 2), "method": method,
            "review": review1}
