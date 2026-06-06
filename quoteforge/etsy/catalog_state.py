"""Live catalog state (written by the Gelato sync, read by pricing).

A small JSON file is the single source of truth for *current* Gelato reality:
per-SKU availability + latest cost. The Gelato sync refreshes it; the frame
catalog + variation pricing read it so a discontinued frame auto-disappears and
a cost change auto-reprices to hold the 60% margin floor — no code edits.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _state_path() -> Path:
    from quoteforge.config import OUTPUT_DIR
    return OUTPUT_DIR / "gelato_state.json"


def load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {"updated": None, "skus": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — corrupt file shouldn't break pricing
        return {"updated": None, "skus": {}}


def save_state(skus: dict) -> Path:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"updated": datetime.now().isoformat(timespec="seconds"), "skus": skus},
        indent=2), encoding="utf-8")
    return p


def sku_override(sku: str) -> dict:
    """Return {'available': bool, 'cost': float|None} for a SKU (empty if none)."""
    return load_state().get("skus", {}).get(sku, {})
