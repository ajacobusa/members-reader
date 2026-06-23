"""REGRESSION (#5): every homepage occasion/gift-set opens a product in a colour the
product actually offers - otherwise the editor silently falls back to White."""
import re
from pathlib import Path


def _occasion_entries():
    src = Path("quoteforge/etsy/listing_preview.py").read_text(encoding="utf-8")
    # {{label:'..', kind:'mug', name:"Accent Mug", color:'Dusty Rose', quote:'..'}}
    return re.findall(r"kind:'(\w+)',\s*name:\"([^\"]+)\",\s*color:'([^']+)'", src)


def _colors(obj):
    return getattr(obj, "colors", None) or getattr(obj, "colours", None) or []


def test_every_occasion_color_is_really_offered():
    from quoteforge.etsy.mug_catalog import MUG_CATALOG
    from quoteforge.etsy.branded_catalog import BRANDED_CATALOG
    mug = {m.name: _colors(m) for m in MUG_CATALOG}
    brand = {b.name: _colors(b) for b in BRANDED_CATALOG}
    entries = _occasion_entries()
    assert entries, "no occasion entries found - regex/source drift"
    bad = []
    for kind, name, color in entries:
        if kind == "mug" and name in mug and color not in mug[name]:
            bad.append((kind, name, color, mug[name]))
        if kind == "branded" and name in brand and color not in brand[name]:
            bad.append((kind, name, color, brand[name]))
    assert not bad, f"occasion colours not offered by the product: {bad}"
