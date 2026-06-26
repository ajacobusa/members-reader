"""Print-quality scoring for customer-supplied photos.

A professional print-on-demand gate does more than a single DPI threshold: it
measures real sharpness, noise, compression and exposure on the ACTUAL pixels and
combines them into one 0-100 quality score with a Pass / Warn / Reject verdict, so
a blurry-but-large photo is caught BEFORE it prints.

Design notes:
- Pure numpy + Pillow (both already in the runtime). No OpenCV/scipy dependency.
- Never raises and never makes a network call: a metric that can't be computed is
  scored neutrally so the gate degrades safely. The Claude-vision component is
  key-gated + TEST_MODE-safe via the existing ai_vision_check.
- Customer-facing: returns plain quality language + a star rating; it NEVER names
  a supplier or print partner.

The verdict drives the upload UX: PASS proceeds, WARN offers enhancement / a
"may look soft" note, REJECT asks for a better photo.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# Component weights (sum = 100). Mirrors a typical POD quality model: resolution
# dominates, sharpness next, then noise/compression/exposure, with an optional
# AI/subject pass. Override via config if you want to re-tune.
_WEIGHTS = {"resolution": 30, "blur": 25, "noise": 15,
            "compression": 10, "exposure": 10, "ai": 10}

# Blur = variance of the Laplacian (high-frequency energy). Computed on a fixed
# long-edge so the score is comparable across images. Calibrated cut points.
_BLUR_VERY_LOW = 80.0      # below: very blurry
_BLUR_GOOD = 150.0         # at/above: acceptably sharp
_BLUR_EXCELLENT = 350.0    # at/above: crisp
_ANALYSIS_LONG_EDGE = 1024


def _gray(image_path) -> np.ndarray | None:
    """Luminance array at a fixed long edge (for scale-stable metrics), or None."""
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            im = im.convert("L")
            im.thumbnail((_ANALYSIS_LONG_EDGE, _ANALYSIS_LONG_EDGE))
            arr = np.asarray(im, dtype=np.float64)
        return arr if arr.ndim == 2 and min(arr.shape) >= 8 else None
    except Exception:  # noqa: BLE001
        return None


def _native_center_crop(image_path, crop: int = 720) -> np.ndarray | None:
    """A NATIVE-resolution centre crop for noise estimation - downscaling averages
    noise away, so noise must be measured at original pixel scale."""
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            im = im.convert("L")
            w, h = im.size
            left, top = max(0, (w - crop) // 2), max(0, (h - crop) // 2)
            im = im.crop((left, top, min(w, left + crop), min(h, top + crop)))
            arr = np.asarray(im, dtype=np.float64)
        return arr if arr.ndim == 2 and min(arr.shape) >= 8 else None
    except Exception:  # noqa: BLE001
        return None


def laplacian_variance(gray: np.ndarray) -> float:
    """Variance of the 3x3 Laplacian - the standard focus/blur measure. Higher =
    sharper. Pure-numpy interior convolution (no scipy/cv2)."""
    g = gray
    lap = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
           - 4.0 * g[1:-1, 1:-1])
    return float(lap.var())


def _blur_score(gray: np.ndarray) -> tuple[float, float]:
    """(0-100 sub-score, raw variance). Maps the variance through the cut points."""
    var = laplacian_variance(gray)
    if var <= _BLUR_VERY_LOW:
        s = 100.0 * (var / _BLUR_VERY_LOW) * 0.45            # 0..45 (very blurry)
    elif var <= _BLUR_GOOD:
        s = 45.0 + 35.0 * (var - _BLUR_VERY_LOW) / (_BLUR_GOOD - _BLUR_VERY_LOW)
    elif var <= _BLUR_EXCELLENT:
        s = 80.0 + 20.0 * (var - _BLUR_GOOD) / (_BLUR_EXCELLENT - _BLUR_GOOD)
    else:
        s = 100.0
    return round(min(100.0, max(0.0, s)), 1), round(var, 1)


def _noise_score(gray: np.ndarray) -> float:
    """0-100. Immerkaer's fast noise-variance estimate: a 3x3 kernel designed to
    cancel image STRUCTURE (edges/detail) and respond only to noise, so a sharp,
    detailed photo is NOT penalised as noisy. Higher score = cleaner."""
    g = gray
    h, w = g.shape
    if h < 4 or w < 4:
        return 80.0
    m = (g[:-2, :-2] - 2.0 * g[:-2, 1:-1] + g[:-2, 2:]
         - 2.0 * g[1:-1, :-2] + 4.0 * g[1:-1, 1:-1] - 2.0 * g[1:-1, 2:]
         + g[2:, :-2] - 2.0 * g[2:, 1:-1] + g[2:, 2:])
    sigma = float(np.sqrt(np.pi / 2.0) / (6.0 * (w - 2) * (h - 2)) * np.sum(np.abs(m)))
    # sigma ~0-2 clean, ~8+ noticeably noisy (0-255 luminance).
    s = 100.0 - max(0.0, sigma - 2.0) * 9.0
    return round(min(100.0, max(0.0, s)), 1)


def _exposure_score(gray: np.ndarray) -> float:
    """0-100. Penalise blown highlights / crushed shadows (clipping) and very low
    contrast (flat/under-exposed)."""
    g = gray
    total = g.size
    # True clipping is 254-255 / 0-1; only penalise once a real fraction clips, so a
    # legitimately bright (high-key) or dark photo isn't false-flagged.
    clipped = (float(np.count_nonzero(g >= 254)) + float(np.count_nonzero(g <= 1))) / total
    contrast = float(g.std())
    s = 100.0 - max(0.0, clipped - 0.05) * 400.0           # penalise only > 5% clipped
    if contrast < 18.0:                                    # genuinely flat / washed-out
        s -= (18.0 - contrast) * 1.5
    return round(min(100.0, max(0.0, s)), 1)


def _compression_score(image_path) -> float:
    """0-100. Estimate JPEG quality from the quantization tables (lower quant =
    higher quality). PNG/TIFF (lossless) score full. Neutral if unknown."""
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            fmt = (im.format or "").upper()
            # Truly lossless formats score full; WEBP can be lossy so it is NOT here
            # (it falls through to the neutral 80 rather than a false 95).
            if fmt in ("PNG", "TIFF", "BMP"):
                return 95.0
            qt = getattr(im, "quantization", None)
        if not qt:
            return 80.0                                     # unknown -> neutral-good
        # Mean of the luminance quantization table: ~2-6 = high quality (q>=90),
        # ~25+ = heavily compressed (q<=50).
        first = qt.get(0) or next(iter(qt.values()))
        mean_q = float(np.mean(first))
        s = 100.0 - (mean_q - 4.0) * 2.2
        return round(min(100.0, max(0.0, s)), 1)
    except Exception:  # noqa: BLE001
        return 80.0


def _resolution_score(effective_dpi: float) -> float:
    """0-100 from effective DPI at the chosen print size. >=300 excellent, 200 the
    professional floor, 150 marginal, below = poor."""
    from quoteforge.config import PREFLIGHT_TARGET_DPI
    target = max(201.0, float(PREFLIGHT_TARGET_DPI or 300))   # guard the 200 floor span
    if effective_dpi >= target:
        return 100.0
    if effective_dpi >= 200:
        return round(85.0 + 15.0 * (effective_dpi - 200) / (target - 200), 1)
    if effective_dpi >= 150:
        return round(65.0 + 20.0 * (effective_dpi - 150) / 50.0, 1)
    return round(max(0.0, 65.0 * (effective_dpi / 150.0)), 1)


def _ai_score(image_path, run_ai: bool) -> tuple[float, str]:
    """(0-100, note) from the existing Claude-vision QC. Neutral (no penalty) when
    AI is unavailable / TEST_MODE, so the gate never depends on a network call."""
    if not run_ai:
        return 75.0, "AI review skipped"
    try:
        from quoteforge.ai.assistant import ai_vision_check
        v = ai_vision_check(image_path)
        if v.get("ok", True):
            return 90.0, v.get("note", "looks good")
        return 45.0, v.get("note", "flagged a likely defect")
    except Exception:  # noqa: BLE001
        return 75.0, "AI review unavailable"


def score_photo(image_path, product_size: str = "", run_ai: bool = True) -> dict:
    """Full print-quality score for a buyer photo at the ordered size.

    Returns a dict with the 0-100 ``score``, a ``verdict`` (pass|warn|reject), a
    1-5 ``stars`` rating, the per-component breakdown, the effective DPI, a
    customer-facing ``message``, and ``recommend_enhance``. Never raises.
    """
    from quoteforge.config import (PHOTO_QUALITY_PASS, PHOTO_QUALITY_REJECT)
    from quoteforge.images.photo_check import check_customer_photo

    res = check_customer_photo(image_path, product_size)
    eff_dpi = float(res.get("effective_dpi") or 0)
    gray = _gray(image_path)

    if gray is None:                                        # unreadable / not found
        return {"ok": False, "score": 0, "verdict": "reject", "stars": 0,
                "effective_dpi": eff_dpi, "components": {}, "weakest": "resolution",
                "message": res.get("reason", "we couldn't read this image - "
                                              "please upload a JPG or PNG"),
                "recommend_enhance": False, "actual_px": res.get("actual_px", (0, 0)),
                "required_px": res.get("required_px", (0, 0))}

    blur_s, blur_var = _blur_score(gray)
    noise_src = _native_center_crop(image_path)            # noise at native scale
    comp = {
        "resolution": _resolution_score(eff_dpi),
        "blur": blur_s,
        "noise": _noise_score(noise_src if noise_src is not None else gray),
        "compression": _compression_score(image_path),
        "exposure": _exposure_score(gray),
        "ai": _ai_score(image_path, run_ai)[0],
    }
    score = round(sum(comp[k] * _WEIGHTS[k] for k in _WEIGHTS) / 100.0, 1)
    if score >= PHOTO_QUALITY_PASS:
        verdict = "pass"
    elif score >= PHOTO_QUALITY_REJECT:
        verdict = "warn"
    else:
        verdict = "reject"
    # No single print-FATAL component may be masked by the weighted average: a very
    # grainy, heavily-compressed, blurry or under-resolution photo prints badly no
    # matter how good the others are. The worst critical component caps the verdict
    # (a near-zero one rejects; a poor one can't be a clean PASS).
    from quoteforge.config import CUSTOMER_PHOTO_MIN_DPI
    fatal = min(comp["resolution"], comp["blur"], comp["noise"], comp["compression"])
    if fatal < 15:
        verdict = "reject"
    elif fatal < 40 and verdict == "pass":
        verdict = "warn"
    # Absolute print-size floor (effective DPI), independent of the score: far below
    # the floor a photo prints terribly no matter how clean.
    floor = float(CUSTOMER_PHOTO_MIN_DPI or 150)
    if eff_dpi and eff_dpi < floor * 0.67:
        verdict = "reject"
    stars = max(1, min(5, round(score / 20.0)))

    # Customer message keyed to the ACTUAL weakest factor (not always "soft").
    worst_key = min(comp, key=comp.get)
    lead = {"resolution": "may look soft at this size (the resolution is low)",
            "blur": "looks a little soft / out of focus",
            "noise": "looks a bit grainy",
            "compression": "is heavily compressed and may show blocky artifacts",
            "exposure": "is a little too dark/bright or low in contrast",
            "ai": "may have an issue our quality review flagged"}
    remedy = {"resolution": "a higher-resolution photo",
              "blur": "a sharper, in-focus photo",
              "noise": "a cleaner, less grainy photo (more light usually helps)",
              "compression": "the original, less-compressed photo",
              "exposure": "a brighter, well-lit photo",
              "ai": "a clearer photo"}
    if verdict == "pass":
        message = "Great - this photo should print beautifully at this size."
    elif verdict == "warn":
        message = (f"This photo {lead[worst_key]}. We can enhance it, or you can "
                   "upload a higher-quality photo.")
    else:
        message = (f"This photo is unlikely to print well - it {lead[worst_key]}. "
                   f"Please upload {remedy[worst_key]} for a great result.")

    return {"ok": verdict != "reject", "score": score, "verdict": verdict,
            "stars": stars, "effective_dpi": round(eff_dpi), "components": comp,
            "weakest": worst_key, "message": message,
            "recommend_enhance": verdict == "warn",
            "actual_px": res.get("actual_px", (0, 0)),
            "required_px": res.get("required_px", (0, 0))}
