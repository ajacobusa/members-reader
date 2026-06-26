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


def _http_get_bytes(url: str, headers: dict | None = None,
                    timeout: int = 60) -> bytes | None:
    """GET a URL and return its body bytes, or None on any problem."""
    try:
        import requests
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:  # noqa: BLE001
        return None
    return None


def _provider_output_bytes(out, headers: dict | None = None) -> bytes | None:
    """Normalise a provider's 'output' field (a hosted URL, a data: URI, or a list
    of either) to raw image bytes."""
    if isinstance(out, (list, tuple)) and out:
        out = out[0]
    if not isinstance(out, str) or not out:
        return None
    if out.startswith("http"):
        return _http_get_bytes(out, headers=headers)
    if out.startswith("data:") and "," in out:
        try:
            import base64
            return base64.b64decode(out.split(",", 1)[1])
        except Exception:  # noqa: BLE001
            return None
    return None


def _upscale_generic(src: Path, target_w: int, target_h: int, scale: float,
                     url: str, key: str) -> bytes | None:
    """A synchronous endpoint (e.g. your own Real-ESRGAN / GFPGAN server): POST the
    image as multipart and get back the upscaled image bytes - or a JSON body
    carrying an output URL / data-URI."""
    try:
        import requests
        with open(src, "rb") as fh:
            resp = requests.post(
                url, headers={"Authorization": f"Bearer {key}"},
                files={"image": fh},
                data={"target_width": target_w, "target_height": target_h,
                      "scale": round(scale, 3)},
                timeout=120)
        if resp.status_code != 200:
            return None
        ctype = (resp.headers.get("content-type") or "").lower()
        if ctype.startswith("image/"):
            return resp.content or None
        try:
            j = resp.json()
        except Exception:  # noqa: BLE001 - not JSON: treat the body as the image
            return resp.content or None
        out = j.get("output") or j.get("url") or j.get("image") or j.get("result")
        return _provider_output_bytes(out)
    except Exception:  # noqa: BLE001
        return None


def _upscale_replicate(src: Path, scale: float, url: str, key: str,
                       model: str) -> bytes | None:
    """Replicate's async Real-ESRGAN: create a prediction with the image as a data
    URI, poll (bounded) until it succeeds, then download the output image."""
    if not model:
        return None
    try:
        import requests, base64, time
        with open(src, "rb") as fh:
            data_uri = "data:image/png;base64," + base64.b64encode(fh.read()).decode()
        endpoint = url or "https://api.replicate.com/v1/predictions"
        headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
        resp = requests.post(endpoint, headers=headers, timeout=30, json={
            "version": model,
            "input": {"image": data_uri, "scale": round(scale, 2)}})
        if resp.status_code not in (200, 201):
            return None
        pred = resp.json()
        status = pred.get("status")
        get_url = (pred.get("urls") or {}).get("get")
        for _ in range(40):                       # ~60s max, then give up -> Lanczos
            if status in ("succeeded", "failed", "canceled"):
                break
            if not get_url:
                return None
            time.sleep(1.5)
            pr = requests.get(get_url, headers=headers, timeout=30)
            if pr.status_code != 200:
                return None
            pred = pr.json()
            status = pred.get("status")
        if status != "succeeded":
            return None
        return _provider_output_bytes(pred.get("output"))
    except Exception:  # noqa: BLE001
        return None


def _ai_upscale(src: Path, target_w: int, target_h: int,
                scale: float = 2.0) -> bytes | None:
    """Pluggable AI super-resolution, dispatched by AI_UPSCALE_PROVIDER. Returns the
    enhanced image bytes, or None on any problem (so the caller falls back to the
    Lanczos baseline). Key-gated + TEST_MODE-safe: never touches the network without
    a real key."""
    from quoteforge.config import TEST_MODE
    try:
        from quoteforge.config import (AI_UPSCALE_API_KEY, AI_UPSCALE_API_URL,
                                       AI_UPSCALE_PROVIDER, AI_UPSCALE_MODEL)
    except Exception:  # noqa: BLE001 — config without the keys: no AI tier
        return None
    if TEST_MODE or not AI_UPSCALE_API_KEY:
        return None
    if (AI_UPSCALE_PROVIDER or "generic") == "replicate":
        return _upscale_replicate(src, scale, AI_UPSCALE_API_URL,
                                  AI_UPSCALE_API_KEY, AI_UPSCALE_MODEL)
    if not AI_UPSCALE_API_URL:
        return None
    return _upscale_generic(src, target_w, target_h, scale,
                            AI_UPSCALE_API_URL, AI_UPSCALE_API_KEY)


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
                from quoteforge.config import (AI_UPSCALE_API_KEY, AI_UPSCALE_API_URL,
                                               AI_UPSCALE_PROVIDER, AI_UPSCALE_MODEL)
                if (AI_UPSCALE_PROVIDER or "generic") == "replicate":
                    ai_on = bool(AI_UPSCALE_API_KEY and AI_UPSCALE_MODEL) and not TEST_MODE
                else:
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
            ai_bytes = _ai_upscale(src, target_w, target_h, scale) if ai_on else None
            used_ai = False
            if ai_bytes:
                # Trust but verify: the provider's output must be a real image at
                # (near) the target size. A garbage / undersized response must NOT
                # cost us the reliable Lanczos baseline.
                try:
                    from io import BytesIO
                    with Image.open(BytesIO(ai_bytes)) as _ai_im:
                        _ai_im.load()
                        _aw, _ah = _ai_im.size
                    if _aw >= target_w * 0.9 and _ah >= target_h * 0.9:
                        dst.write_bytes(ai_bytes)
                        method = "ai"
                        used_ai = True
                except Exception:  # noqa: BLE001 - unusable bytes -> Lanczos
                    used_ai = False
            if not used_ai:
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
