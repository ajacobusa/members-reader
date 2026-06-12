"""AI-assisted print-quality check + order validation before Gelato submission.

Two gates protect every order that includes a customer photo:
  1. Deterministic file validation - format (JPG/PNG/PDF/TIFF) and resolution vs.
     the chosen print size (needs >= MIN_DPI effective DPI for a sharp print).
  2. AI vision review (Claude) - flags blur, wrong subject, low contrast, etc.

assess_photo() combines both into approve | hold | reject. validate_order_for_gelato()
is the final pre-submission check: address complete, product set, a print file
attached, and quality not rejected. Gelato's v3/orders accepts the customer file
by URL (items[].files[].url), so the approved JPG is sent straight to print.
"""
from __future__ import annotations
from pathlib import Path

MIN_DPI = 150                       # Gelato-safe minimum for a crisp print
SUPPORTED = (".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff")


def _size_inches(size: str) -> tuple[float, float]:
    """Parse a size string like '18x24' into (width, height) inches; 18x24 default."""
    try:
        a, b = (size or "18x24").lower().split("x")[0:2]
        return float(a), float(b.split()[0])
    except (ValueError, IndexError):
        return 18.0, 24.0


def validate_print_file(path, size: str = "18x24", min_dpi: int = MIN_DPI) -> dict:
    """Format + resolution check for a print file against the chosen size."""
    p = Path(path)
    out = {"ok": False, "format_ok": False, "resolution_ok": None,
           "width": None, "height": None, "dpi": None, "issues": []}
    if not p.exists():
        out["issues"].append("file not found")
        return out
    ext = p.suffix.lower()
    if ext not in SUPPORTED:
        out["issues"].append(f"unsupported format {ext} (use JPG/PNG/PDF/TIFF)")
        return out
    out["format_ok"] = True
    if ext == ".pdf":
        # Can't measure raster DPI of a PDF here; treat as ok, verified on proof.
        out["resolution_ok"] = None
        out["ok"] = True
        out["issues"].append("PDF - resolution verified on proof")
        return out
    try:
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
    except Exception as exc:  # noqa: BLE001
        out["issues"].append(f"could not read image ({type(exc).__name__})")
        return out
    iw, ih = _size_inches(size)
    need_w, need_h = int(iw * min_dpi), int(ih * min_dpi)
    big_ok = max(w, h) >= max(need_w, need_h)
    small_ok = min(w, h) >= min(need_w, need_h)
    eff_dpi = round(min(w / iw, h / ih)) if iw and ih else 0
    out.update({"width": w, "height": h, "dpi": eff_dpi})
    out["resolution_ok"] = bool(big_ok and small_ok)
    if not out["resolution_ok"]:
        out["issues"].append(
            f"{w}x{h}px (~{eff_dpi} DPI) is too low for a sharp {iw:g}x{ih:g}\" "
            f"print; need >= {need_w}x{need_h}px ({min_dpi} DPI)")
    out["ok"] = out["resolution_ok"] is not False
    return out


def assess_photo(path, size: str = "18x24", run_ai: bool = True) -> dict:
    """Full quality assessment: file validation + AI vision -> approve|hold|reject."""
    v = validate_print_file(path, size)
    ai = {"ok": True, "note": "AI vision skipped"}
    if run_ai and v["format_ok"] and Path(path).suffix.lower() != ".pdf":
        try:
            from quoteforge.ai.assistant import ai_vision_check
            ai = ai_vision_check(path)
        except Exception as exc:  # noqa: BLE001
            ai = {"ok": True, "note": f"AI vision unavailable ({type(exc).__name__})"}
    reasons = list(v["issues"])
    if not ai.get("ok", True):
        reasons.append(f"AI: {ai.get('note', 'flagged')}")
    if not v["format_ok"]:
        decision = "reject"
    elif v["resolution_ok"] is False:
        decision = "hold"          # ask for a higher-resolution original
    elif not ai.get("ok", True):
        decision = "hold"          # AI flagged a likely defect
    else:
        decision = "approve"
    return {"decision": decision, "validation": v, "ai": ai, "reasons": reasons}


def ai_focal_point(path) -> dict:
    """Estimate the subject's center (for auto-centering in the frame).

    Returns {x, y} as fractions 0..1 (0.5,0.5 = image center). Uses Claude vision
    when available; otherwise returns center. Never raises."""
    from pathlib import Path as _P
    p = _P(path)
    default = {"x": 0.5, "y": 0.5, "source": "center"}
    try:
        from quoteforge.config import TEST_MODE, ANTHROPIC_API_KEY, CLAUDE_MODEL
        if TEST_MODE or not ANTHROPIC_API_KEY or not p.exists() \
                or p.suffix.lower() == ".pdf":
            return default
        import base64, re
        from quoteforge.quotes.generator import _client, _invoke
        ext = p.suffix.lower().lstrip(".")
        media = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        msg = _invoke(
            _client(), operation="ai_focal", model=CLAUDE_MODEL, max_tokens=40,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": media, "data": b64}},
                {"type": "text", "content": (
                    "Find the main subject (face/person/focal object). Reply with "
                    "ONLY its center as 'x,y' where x and y are decimals 0..1 "
                    "(left-to-right, top-to-bottom). Example: 0.42,0.30")}]}])
        text = "".join(getattr(b, "text", "") for b in msg.content).strip()
        m = re.search(r"([01]?\.?\d+)\s*,\s*([01]?\.?\d+)", text)
        if m:
            x = min(1.0, max(0.0, float(m.group(1))))
            y = min(1.0, max(0.0, float(m.group(2))))
            return {"x": round(x, 3), "y": round(y, 3), "source": "ai"}
    except Exception:  # noqa: BLE001
        pass
    return default


def reupload_request(assessment: dict, recipient: str = "") -> str:
    """Customer-facing message asking for a better photo (AI-written if available)."""
    reasons = "; ".join(assessment.get("reasons", [])) or "image quality"
    try:
        from quoteforge.ai.assistant import ai_text
        txt = ai_text(
            "Write a short, friendly 2-sentence note asking a customer to re-upload "
            "a higher-quality photo for their wall-art order. Be specific but kind. "
            f"Reason(s): {reasons}.", "reupload_request", max_tokens=120)
        if txt and txt.strip():
            return txt.strip()
    except Exception:  # noqa: BLE001
        pass
    return ("To make sure your print looks crisp, we need a higher-quality photo - "
            f"{reasons}. Please reply with a higher-resolution original and we'll "
            "send your free proof right away.")


REQUIRED_ADDRESS = ("name", "address", "city", "postCode", "country")


def file_sha256(path) -> str:
    """SHA-256 of a local file, or '' when it does not exist / can't be read."""
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def hashable_print_file(order: dict) -> str:
    """The local file that will actually be printed, when one exists on disk:
    the customer's print_file, else a local artwork path. '' when remote-only."""
    for key in ("print_file", "artwork_url"):
        p = order.get(key) or ""
        if p and "://" not in str(p) and Path(p).exists():
            return str(p)
    return ""


def validate_order_for_gelato(order: dict) -> dict:
    """Final pre-submission validation. Returns {ok, issues}."""
    issues = []
    addr = order.get("recipient_address") or {}
    if isinstance(addr, dict):
        missing = [f for f in REQUIRED_ADDRESS if not str(addr.get(f, "")).strip()]
        if missing:
            issues.append(f"incomplete shipping address: {', '.join(missing)}")
    else:
        issues.append("missing shipping address")
    if not (order.get("gelato_product_uid") or order.get("product_uid")):
        issues.append("no Gelato product selected")
    if not (order.get("artwork_url") or order.get("print_file")):
        issues.append("no print file attached")
    if (order.get("print_quality") or "").lower() == "reject":
        issues.append("print file failed quality check")
    # Parity gate: the file the customer APPROVED must be the file we print.
    # (Orders approved before the hash feature have no hash - not blocked.)
    approved_hash = order.get("proof_file_hash") or ""
    if approved_hash:
        current = hashable_print_file(order)
        if current and file_sha256(current) != approved_hash:
            issues.append("print file changed since customer approval - "
                          "re-approve required before production")
    return {"ok": not issues, "issues": issues}


def format_assessment_text(a: dict) -> str:
    """Render a photo assessment as a short plain-text block."""
    v = a["validation"]
    lines = ["Print-quality assessment", "-" * 32,
             f"  Decision   : {a['decision'].upper()}",
             f"  Format OK  : {v['format_ok']}",
             f"  Resolution : {v['width']}x{v['height']}px"
             + (f" (~{v['dpi']} DPI)" if v.get('dpi') else ""),
             f"  AI vision  : {a['ai'].get('note', '')}"]
    if a["reasons"]:
        lines.append("  Issues     : " + "; ".join(a["reasons"]))
    return "\n".join(lines)
