"""Final product QC - run BEFORE the customer proof is sent.

Combines the deterministic print preflight (DPI / size / aspect / colour mode)
with an optional Claude vision review (cut-off text, misspellings, blurriness).
The deterministic check is the authoritative gate; AI vision only adds a flag.
Nothing reaches the customer until this passes.
"""
from __future__ import annotations


def final_qc(artwork_path, size_key: str = "") -> dict:
    """Return {'ok': bool, 'checks': [...], 'ai': {...}, 'fails': [...]}."""
    from quoteforge.images.preflight import run_preflight
    pf = run_preflight(artwork_path, size_key)
    checks = pf.get("checks", [])
    ok = bool(pf.get("ok", True))
    fails = [c["name"] for c in checks if not c.get("ok", True)]

    ai = {"ok": True, "note": "skipped"}
    try:
        from quoteforge.ai.assistant import ai_vision_check
        ai = ai_vision_check(artwork_path)
        if not ai.get("ok", True):
            ok = False
            fails.append("AI vision: " + ai.get("note", "flagged"))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": ok, "checks": checks, "ai": ai, "fails": fails}
