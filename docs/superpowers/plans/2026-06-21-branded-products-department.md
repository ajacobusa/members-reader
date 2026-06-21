# Custom Branded Products — Department First Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a real, sellable "Custom Branded Products" department (totes, bottles, tumblers, mouse pads, notebooks, journals, stickers, phone cases, keychains) following the exact Wall-Art/Apparel pattern, reusing the design editor + Layout Studio.

**Architecture:** A self-contained `branded_catalog.py` (mirrors `apparel_catalog.py`) defines products + variants priced to the 60% floor and the Gelato ingest/guard seam. The storefront gains a `deptBranded` pane + `_branded_section()`; the shared editor gains an `IS_BRANDED` mode that reuses `drawArt`, the movable print frame, and the whole Layout Studio over a flat product field. Net-new (360 wrap, bundles, phone-case model axis, pattern-tile) is deferred.

**Tech Stack:** Python catalog/pricing, Gelato variant resolver (env/JSON UID maps, TEST_MODE safe), HTML/Canvas storefront f-string in `listing_preview.py`, pytest string/integration tests, Higgsfield image gen, Claude_Preview MCP for live verification.

**Reference spec:** `docs/superpowers/specs/2026-06-21-new-departments-mugs-calendars-branded.md`. Template module: `quoteforge/etsy/apparel_catalog.py`.

**Conventions (every task):** after editing the storefront f-string, `python -m quoteforge.admin rebuild-site` then assert on the regenerated `docs/index.html` (tests build their own copy). Targeted run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_*.py`. Source-integrity net after f-string edits: `quoteforge_tests/test_source_integrity.py`. Hard rule: no `gelato`/`printify`/`printful`/`etsy` in any customer-facing string. Commit after each green task. Create the branch `feat/branded-products-department` off `main` BEFORE Task 1.

---

## File structure

- Create `quoteforge/etsy/branded_catalog.py` — products, variants, pricing, dims, ingest seam, guard.
- Create `quoteforge_tests/test_branded_catalog.py` and `quoteforge_tests/test_branded_storefront.py`.
- Modify `quoteforge/automation/pipeline_orchestrator.py` + `quoteforge/automation/webhook_server.py` — call `enrich_branded_order` at the same seam as `enrich_apparel_order`.
- Modify `quoteforge/etsy/margin_guard.py` — add a `branded` audit loop.
- Modify `quoteforge/automation/catalog_sync.py` — include branded variations.
- Modify `quoteforge/etsy/listing_preview.py` — `BRANDEDCOLOR` additions, `_branded_section()`, data-prep, nav/deptcard/deptswitch/pane, `selectDept` branch, `IS_BRANDED` editor mode, `drawArt` flat-field branch.
- Add brand assets `quoteforge/brand/dept-branded.jpg` + `tile-<product_id>.jpg` (Higgsfield).

---

## Task 1: branded_catalog.py — products, variants, pricing, dimensions

**Files:** Create `quoteforge/etsy/branded_catalog.py`; Test `quoteforge_tests/test_branded_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# quoteforge_tests/test_branded_catalog.py
from quoteforge.etsy.branded_catalog import (
    BRANDED_CATALOG, build_branded_variations, branded_dimensions_for, get_product)


def test_catalog_has_core_products():
    ids = {p.product_id for p in BRANDED_CATALOG}
    for pid in ("tote", "bottle", "tumbler", "mousepad", "notebook",
                "journal", "sticker", "phonecase", "keychain"):
        assert pid in ids, pid


def test_every_variant_clears_the_margin_floor():
    from quoteforge.config import TARGET_MARGIN_PCT
    vs = build_branded_variations()
    assert vs, "no variants built"
    for v in vs:
        assert v.price > v.gelato_cost            # never sells at/under cost
        assert v.margin_pct >= TARGET_MARGIN_PCT   # holds the 60% floor


def test_dimensions_lookup_falls_back_safely():
    assert branded_dimensions_for("tote")[0] > 0
    assert branded_dimensions_for("does-not-exist")[0] > 0   # safe default
```

- [ ] **Step 2: Run, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_catalog.py`
Expected: FAIL (module not found).

- [ ] **Step 3: Create `quoteforge/etsy/branded_catalog.py`**

```python
"""Custom Branded Products family (Gelato-fulfilled).

A self-contained parallel module modeled on apparel_catalog.py. Branded merch
differs from apparel only in shape:
  * one product line per item (no gender x tier explosion); each item is one
    listing with its own print bound (branded_dimensions_for).
  * variants are (size/variant x colour); flat products are size "One Size".
Costs are seeded (modeled) and overridden live by the Gelato sync; pricing always
re-derives from current cost to hold the 60% net-margin floor. Seed SKUs ship as
GEL-* placeholders mapped to real Gelato UIDs before go-live (verify_branded_mappings).
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BRANDED_DIMS: tuple[int, int] = (3000, 3000)


@dataclass
class BrandedProduct:
    """One sellable branded product line with its sizes, colours, print geometry,
    seed cost and recommended Gelato blank."""
    product_id: str            # unique: "tote", "bottle", ...
    name: str                  # customer-facing: "Organic Cotton Tote Bag"
    type_name: str             # short type: "Tote Bag"
    category: str              # storefront facet: "Bags", "Drinkware", ...
    sizes: list[str]
    colors: list[str]          # LIGHT shades first
    base_cost: float           # seed Gelato cost (USD), live-overridable
    sku_prefix: str            # "GEL-TOTE"
    brand: str = ""            # Gelato blank brand/style (server-side only)
    tier: str = "Classic"      # Value | Classic | Premium
    width_px: int = DEFAULT_BRANDED_DIMS[0]
    height_px: int = DEFAULT_BRANDED_DIMS[1]
    placement: str = "front"


# (product_id, name, type_name, category, sizes, colors, base_cost, brand, tier, w, h)
_BRANDED_TYPES = [
    ("tote", "Organic Cotton Tote Bag", "Tote Bag", "Bags",
     ["One Size"], ["Natural", "White", "Sand", "Sage", "Navy", "Black"],
     7.0, "Gelato Organic Tote", "Value", 3000, 3600),
    ("bottle", "Insulated Stainless Water Bottle", "Water Bottle", "Drinkware",
     ["20oz"], ["White", "Silver", "Black", "Navy", "Red"],
     12.0, "Gelato Steel Bottle", "Premium", 3600, 2400),
    ("tumbler", "Insulated Stainless Tumbler", "Tumbler", "Drinkware",
     ["20oz", "30oz"], ["White", "Silver", "Black", "Navy", "Forest Green"],
     14.0, "Gelato Steel Tumbler", "Premium", 3600, 2200),
    ("mousepad", "Rectangular Mouse Pad", "Mouse Pad", "Desk",
     ["9x7", "12x10"], ["White"], 6.0, "Gelato Mouse Pad", "Value", 2700, 2100),
    ("notebook", "Softcover Notebook", "Notebook", "Stationery",
     ["A5"], ["White", "Cream", "Black", "Navy"], 5.0, "Gelato Softcover", "Value", 1740, 2490),
    ("journal", "Hardcover Journal", "Journal", "Stationery",
     ["A5"], ["Black", "Navy", "Maroon", "Forest Green", "Sand"],
     9.0, "Gelato Hardcover", "Premium", 1740, 2490),
    ("sticker", "Die-Cut Vinyl Sticker", "Sticker", "Stickers",
     ["2x2", "3x3", "4x4"], ["White"], 2.0, "Gelato Vinyl Sticker", "Value", 1200, 1200),
    ("phonecase", "Tough Phone Case", "Phone Case", "Tech",
     ["iPhone", "Samsung"], ["White", "Black"], 8.0, "Gelato Tough Case", "Classic", 1800, 3600),
    ("keychain", "Metal Keychain", "Keychain", "Accessories",
     ["Rectangle", "Circle"], ["Silver"], 4.0, "Gelato Metal Keychain", "Value", 600, 600),
]


def _build_catalog() -> list[BrandedProduct]:
    out: list[BrandedProduct] = []
    for pid, name, type_name, cat, sizes, colors, cost, brand, tier, w, h in _BRANDED_TYPES:
        out.append(BrandedProduct(
            product_id=pid, name=name, type_name=type_name, category=cat,
            sizes=list(sizes), colors=list(colors), base_cost=cost,
            sku_prefix=f"GEL-{pid.upper()}", brand=brand, tier=tier,
            width_px=w, height_px=h))
    return out


BRANDED_CATALOG: list[BrandedProduct] = _build_catalog()


@dataclass
class BrandedVariant:
    product_id: str
    name: str
    size: str
    color: str
    gelato_sku: str
    gelato_cost: float
    price: float
    margin_pct: int
    placement: str = "front"


def get_product(product_id: str) -> BrandedProduct | None:
    key = (product_id or "").strip().lower()
    return next((p for p in BRANDED_CATALOG if p.product_id == key), None)


def branded_dimensions_for(product_id: str) -> tuple[int, int]:
    """(width_px, height_px) of the print area for a product, or a safe default."""
    p = get_product(product_id)
    return (p.width_px, p.height_px) if p else DEFAULT_BRANDED_DIMS


def _variant_sku(p: BrandedProduct, size: str, color: str) -> str:
    part = lambda s: s.upper().replace(" ", "-")
    return f"{p.sku_prefix}-{part(size)}-{part(color)}"


def _variant_cost(p: BrandedProduct, sku: str) -> float | None:
    """Seed cost with any live Gelato override; None when discontinued."""
    from quoteforge.etsy.catalog_state import sku_override
    ov = sku_override(sku)
    if ov and ov.get("available") is False:
        return None
    if ov and ov.get("cost") is not None:
        return round(ov["cost"], 2)
    return round(p.base_cost, 2)


def _list_floor(floor_pct: float | None) -> float:
    from quoteforge.config import LIST_MARGIN_PCT, TARGET_MARGIN_PCT
    if floor_pct is not None:
        return max(floor_pct, TARGET_MARGIN_PCT)
    return max(LIST_MARGIN_PCT, TARGET_MARGIN_PCT)


def build_branded_variations(floor_pct: float | None = None) -> list[BrandedVariant]:
    """Every sellable branded variant (product x size x colour), priced to clear
    the 60% net-margin floor. Discontinued variants are dropped."""
    from quoteforge.etsy.variations import min_price_for_margin, net_margin_pct
    floor = _list_floor(floor_pct)
    out: list[BrandedVariant] = []
    for p in BRANDED_CATALOG:
        for size in p.sizes:
            for color in p.colors:
                sku = _variant_sku(p, size, color)
                cost = _variant_cost(p, sku)
                if cost is None:
                    continue
                price = min_price_for_margin(cost, floor)
                out.append(BrandedVariant(
                    product_id=p.product_id, name=p.name, size=size, color=color,
                    gelato_sku=sku, gelato_cost=cost, price=price,
                    margin_pct=net_margin_pct(price, cost), placement=p.placement))
    return out


def branded_skus() -> list[str]:
    return sorted({_variant_sku(p, s, c)
                   for p in BRANDED_CATALOG for s in p.sizes for c in p.colors})
```

- [ ] **Step 4: Run, verify it passes**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_catalog.py`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/branded_catalog.py quoteforge_tests/test_branded_catalog.py
git commit -m "feat(branded): catalog + variants priced to the 60% floor"
```

---

## Task 2: branded_catalog.py — Gelato ingest seam + placeholder guard

**Files:** Modify `quoteforge/etsy/branded_catalog.py`; Test `quoteforge_tests/test_branded_catalog.py`

- [ ] **Step 1: Add failing tests**

```python
def test_parse_and_resolve_sku_round_trip():
    from quoteforge.etsy.branded_catalog import parse_branded_format, resolve_branded_sku
    assert parse_branded_format("Organic Cotton Tote Bag - Natural") == ("tote", "Natural")
    assert parse_branded_format("Framed - Oak") == (None, None)          # not branded
    assert resolve_branded_sku("Organic Cotton Tote Bag - Natural", "One Size") \
        == "GEL-TOTE-ONE-SIZE-NATURAL"
    assert resolve_branded_sku("Organic Cotton Tote Bag - Natural", "BadSize") is None


def test_enrich_branded_order_merges_fields_or_empty():
    from quoteforge.etsy.branded_catalog import enrich_branded_order
    out = enrich_branded_order({"material": "Organic Cotton Tote Bag - Natural", "size": "One Size"})
    assert out["product_type"] == "branded" and out["product_id"] == "tote"
    assert out["color"] == "Natural" and out["gelato_sku"] == "GEL-TOTE-ONE-SIZE-NATURAL"
    assert out["gelato_cost"] > 0
    assert enrich_branded_order({"material": "Framed - Oak"}) == {}     # non-branded untouched


def test_verify_branded_mappings_reports_placeholders():
    from quoteforge.etsy.branded_catalog import verify_branded_mappings
    rep = verify_branded_mappings()
    assert rep["total"] > 0
    assert set(("total", "configured", "placeholder_count", "placeholders", "all_real")) <= set(rep)
```

- [ ] **Step 2: Run, verify fail**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_catalog.py -k "parse or enrich or verify"`
Expected: FAIL (functions undefined).

- [ ] **Step 3: Append the ingest seam + guard to `branded_catalog.py`**

```python
def parse_branded_format(fmt: str) -> tuple[str | None, str | None]:
    """('Organic Cotton Tote Bag - Natural') -> (product_id, colour); (None, None)
    for anything that is not a real branded format (so apparel/wall-art are safe)."""
    if not fmt or " - " not in fmt:
        return (None, None)
    name, _, color = fmt.partition(" - ")
    p = next((x for x in BRANDED_CATALOG if x.name == name.strip()), None)
    return (p.product_id, color.strip()) if p else (None, None)


def branded_sku_for(product_id: str, size: str, color: str) -> str | None:
    p = get_product(product_id)
    if not p or size not in p.sizes or color not in p.colors:
        return None
    return _variant_sku(p, size, color)


def resolve_branded_sku(fmt: str, size: str) -> str | None:
    pid, color = parse_branded_format(fmt)
    if not pid:
        return None
    return branded_sku_for(pid, size, color)


def enrich_branded_order(order_data: dict) -> dict:
    """Merge branded fields into an order (product_type, product_id, color,
    gelato_sku, gelato_cost, gelato_product_uid). {} for non-branded orders.
    Single ingest seam — call once where order_data is assembled."""
    fmt = (order_data.get("material") or order_data.get("fmt")
           or order_data.get("product_format") or order_data.get("format") or "")
    size = (order_data.get("product_size") or order_data.get("size") or "")
    pid, color = parse_branded_format(fmt)
    if not pid:
        return {}
    sku = branded_sku_for(pid, size, color)
    out: dict = {"product_type": "branded", "product_id": pid,
                 "color": color, "material": fmt, "gelato_sku": sku}
    p = get_product(pid)
    if p and sku:
        cost = _variant_cost(p, sku)
        if cost is not None:
            out["gelato_cost"] = cost
    from quoteforge.automation.gelato_variant_resolver import resolve_variant_uid
    uid = resolve_variant_uid(sku, pid, color, size)
    if uid:
        out["gelato_product_uid"] = uid
    return out


def verify_branded_mappings() -> dict:
    """Every branded variant GO-LIVE READY when its specific UID is statically
    mapped (GELATO_UID_MAP) OR its product family is mapped (resolved dynamically).
    Independent of the print + apparel guards."""
    from quoteforge.automation.gelato_sync import _uid_map
    from quoteforge.automation.gelato_variant_resolver import family_covered
    uid_map = _uid_map()
    vs = build_branded_variations()
    placeholders = []
    for v in vs:
        st = uid_map.get(v.gelato_sku)
        if st and not str(st).upper().startswith("GEL-"):
            continue
        if family_covered(v.product_id):
            continue
        placeholders.append(v.gelato_sku)
    total = len(vs)
    return {"total": total, "configured": total - len(placeholders),
            "placeholder_count": len(placeholders), "placeholders": placeholders,
            "all_real": not placeholders}
```

Note: `family_covered(v.product_id)` uses the same resolver as apparel; until branded families are added to `GELATO_PRODUCT_FAMILY_MAP`, the guard reports placeholders (correct pre-go-live, exactly like apparel).

- [ ] **Step 4: Run, verify pass**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_catalog.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/branded_catalog.py quoteforge_tests/test_branded_catalog.py
git commit -m "feat(branded): Gelato ingest seam + placeholder guard"
```

---

## Task 3: Wire the ingest seam into the order pipeline

**Files:** Modify `quoteforge/automation/pipeline_orchestrator.py`, `quoteforge/automation/webhook_server.py`; Test `quoteforge_tests/test_branded_catalog.py`

- [ ] **Step 1: Find the apparel seam.** Run: `grep -n "enrich_apparel_order" quoteforge/automation/pipeline_orchestrator.py quoteforge/automation/webhook_server.py`. At EACH call site, branded is enriched right after apparel (apparel returns {} for branded and vice-versa, so order is irrelevant).

- [ ] **Step 2: Write the failing test**

```python
def test_pipeline_and_webhook_call_branded_enrich():
    import quoteforge.automation.pipeline_orchestrator as po
    import quoteforge.automation.webhook_server as ws
    import inspect
    assert "enrich_branded_order" in inspect.getsource(po)
    assert "enrich_branded_order" in inspect.getsource(ws)
```

- [ ] **Step 3: Run, verify fail.** `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_catalog.py::test_pipeline_and_webhook_call_branded_enrich` → FAIL.

- [ ] **Step 4: Add the call beside each `enrich_apparel_order` use.** Where the code does e.g. `order_data.update(enrich_apparel_order(order_data))`, add immediately after:

```python
        from quoteforge.etsy.branded_catalog import enrich_branded_order
        order_data.update(enrich_branded_order(order_data))
```

Match the existing import style at that site (top-of-file import if apparel is imported at top). Apply at every site found in Step 1.

- [ ] **Step 5: Run, verify pass** (and the apparel pipeline tests still pass):

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_catalog.py quoteforge_tests/test_apparel_fulfillment.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/automation/pipeline_orchestrator.py quoteforge/automation/webhook_server.py quoteforge_tests/test_branded_catalog.py
git commit -m "feat(branded): wire enrich_branded_order into order ingest"
```

---

## Task 4: margin guard + catalog sync include branded

**Files:** Modify `quoteforge/etsy/margin_guard.py`, `quoteforge/automation/catalog_sync.py`; Test `quoteforge_tests/test_branded_catalog.py`

- [ ] **Step 1: Read the apparel audit loop.** `grep -n "apparel" quoteforge/etsy/margin_guard.py quoteforge/automation/catalog_sync.py`.

- [ ] **Step 2: Write the failing test**

```python
def test_margin_guard_includes_branded():
    from quoteforge.etsy.margin_guard import audit_catalog  # the audit entry (confirm name in Step 1)
    rows = audit_catalog()
    assert any(r.get("kind") == "branded" for r in rows)
```

(If the audit function has a different name/shape, adapt the assertion to call the real one found in Step 1 and assert a branded row appears.)

- [ ] **Step 3: Run, verify fail.**

- [ ] **Step 4: Add a branded loop** alongside the apparel block in `margin_guard.py` audit (mirror the `{'kind':'apparel', ...}` loop using `build_branded_variations()` → each row `{'kind':'branded','sku':v.gelato_sku,'price':v.price,'cost':v.gelato_cost,'margin_pct':v.margin_pct}` consistent with the existing row shape), and add `build_branded_variations()` into `catalog_sync.build_local_catalog` next to `build_apparel_variations()` (same enrich/diff treatment).

- [ ] **Step 5: Run, verify pass.** `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_catalog.py quoteforge_tests/test_margin*.py` → PASS.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/etsy/margin_guard.py quoteforge/automation/catalog_sync.py quoteforge_tests/test_branded_catalog.py
git commit -m "feat(branded): include branded in margin guard + catalog sync"
```

---

## Task 5: Storefront colours for branded base materials

**Files:** Modify `quoteforge/etsy/listing_preview.py` (`APPARELCOLOR` map ~line 4499); Test `quoteforge_tests/test_branded_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
# quoteforge_tests/test_branded_storefront.py
from pathlib import Path
from PIL import Image


def _page(tmp_path) -> str:
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    return build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                           out_path=tmp_path / "h.html", frame_picker=True).read_text(encoding="utf-8")


def test_branded_base_colours_have_swatches(tmp_path):
    # REGRESSION: branded base materials (Natural/Cream/Silver) need hex swatches
    # in the shared colour map so the editor renders them.
    h = _page(tmp_path)
    for c in ('"Natural"', '"Cream"', '"Silver"'):
        assert c in h, c
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Add the three hexes to `APPARELCOLOR`** (the shared map, line ~4503). Append before the closing `}}`:

```
   "Natural":"#e7ddc7","Cream":"#f3ecd9","Silver":"#c9ccce",
```

- [ ] **Step 4: Rebuild + run.** `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_branded_storefront.py::test_branded_base_colours_have_swatches` → PASS.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_branded_storefront.py
git commit -m "feat(branded): add Natural/Cream/Silver swatches to the colour map"
```

---

## Task 6: Storefront `_branded_section()` + data-prep

**Files:** Modify `quoteforge/etsy/listing_preview.py`; Test `quoteforge_tests/test_branded_storefront.py`

This mirrors `_apparel_section()` (listing_preview.py:915+) but flatter (no gender split; facets are Category/Type/Colour/Size).

- [ ] **Step 1: Write the failing test**

```python
def test_branded_section_renders_products_and_facets(tmp_path):
    # REGRESSION: branded section renders a tile per product with data-* facets +
    # a faceted filter bar, and a 'from' price; no supplier leak.
    h = _page(tmp_path)
    assert 'id="branded"' in h or 'id="deptBranded"' in h
    assert 'class="brandcard"' in h
    assert h.count('data-bpid="') >= 9                 # a tile per product
    assert 'data-bpid="tote"' in h and 'data-bpid="bottle"' in h
    assert 'class="brandfilter"' in h or 'id="bfCat"' in h   # facet bar
    assert 'shopBranded(' in h                          # tile opens the editor
    assert "gelato" not in h.lower() and "printify" not in h.lower()
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Read `_apparel_section` (listing_preview.py:915-1060)** to copy its structure exactly, then add a Python builder `_branded_section(photos)` near it that:
  - imports `BRANDED_CATALOG`, `build_branded_variations`; computes a per-product cheapest `from` price (min variant price per `product_id`).
  - renders a hero band (reuse the apparel hero style) + a faceted filter bar with selects `bfCat` (Category), `bfType` (Type), `bfColor`, `bfSize` populated from the catalog distinct values, and an empty-state `id="bfNoMatch"`.
  - renders one `<button class="brandcard" data-bpid="{p.product_id}" data-cat="{p.category}" data-type="{p.type_name}" data-colors="{','.join(p.colors)}" data-sizes="{','.join(p.sizes)}" onclick="shopBranded('{p.name}','{p.colors[0]}')">` per product, with photo `photos.get(p.product_id)` or a neutral SVG fallback, the name, the `from $X`, and colour swatch dots (reuse the apparel swatch-dot markup driven by `APPARELCOLOR`).

  Provide the exact builder by adapting `_apparel_section`; keep every customer-facing string supplier/marketplace-free (no brand field on the page).

- [ ] **Step 4: Add data-prep in `build_shop_home`** next to the apparel block (near listing_preview.py:1300-1433): build `branded_formats_json` = `json.dumps([{ "name": f"{p.name} - {c}", "price": <cheapest variant price for that product+colour> } ...])` and per-product tile photos `_branded_photos[pid] = _emit(brand/f"tile-{pid}.jpg", ...)` with the SVG fallback when absent. Embed `const BRANDED_FORMATS = {branded_formats_json};` and `const BRANDED_DIMS = {branded_dims_json};` (a `{product_id:[w,h]}` map from `branded_dimensions_for`) near `APPAREL_FORMATS` (listing_preview.py:3272).

- [ ] **Step 5: Rebuild + run.** Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_branded_storefront.py
git commit -m "feat(branded): storefront section + data-prep"
```

---

## Task 7: Department chrome (nav, card, switch, pane, selectDept)

**Files:** Modify `quoteforge/etsy/listing_preview.py`; Test `quoteforge_tests/test_branded_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
def test_branded_is_a_third_department(tmp_path):
    # REGRESSION: Branded is a co-equal department (nav link, dept card, switch,
    # pane) selectable alongside Wall Art and Apparel.
    h = _page(tmp_path)
    assert 'href="#branded"' in h
    assert 'class="deptcard deptbranded"' in h or 'deptbranded' in h
    assert 'id="deptBranded"' in h                      # its own pane
    assert "selectDept('branded')" in h                 # switchable
    assert h.count("selectDept(") >= 3                  # wall + apparel + branded
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Add the three nav surfaces** (mirror apparel at listing_preview.py:2598-2599, 2625-2645, 2688-2692): a nav link `<a href="#branded" onclick="selectDept('branded')">🎁 Branded</a>`, a `<a class="deptcard deptbranded">` card with `dept_branded_src` photo + title/sub/go, and a deptswitch button `.dsbranded`. Add the pane `<div id="deptBranded" class="deptpane">{_branded_section(_branded_photos)}</div>` after `deptApparel` (listing_preview.py:2724).

- [ ] **Step 4: Extend `selectDept(d)` (listing_preview.py:3586-3598)** to handle `'branded'` (show `deptBranded`, toggle `.dsbranded`), and `showAllDepartments()` (3599-3605) to also hide `deptBranded`. Add the dept-card photo prep `dept_branded_src` in `build_shop_home` (mirror `dept_app_src`, listing_preview.py:1392-1394).

- [ ] **Step 5: Rebuild + run.** Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_branded_storefront.py
git commit -m "feat(branded): department nav, card, switch, pane"
```

---

## Task 8: Editor mode (IS_BRANDED) reusing drawArt + Layout Studio

**Files:** Modify `quoteforge/etsy/listing_preview.py`; Test `quoteforge_tests/test_branded_storefront.py` + live verify

The branded editor reuses the apparel editor path but draws a FLAT product field instead of a garment silhouette. Strategy: keep `IS_APPAREL` semantics for the print-bound + Layout Studio, and add `IS_BRANDED` that rides the same branches; only the backdrop differs.

- [ ] **Step 1: Write the failing test**

```python
def test_branded_editor_mode_wired(tmp_path):
    # REGRESSION: shopBranded opens the editor in branded mode, reusing the print
    # frame + Layout Studio over a flat product field (no garment silhouette).
    h = _page(tmp_path)
    assert "let IS_BRANDED" in h
    assert "function shopBranded" in h
    assert "BRANDED_FORMATS" in h and "BRANDED_DIMS" in h
    assert "_drawBrandedField" in h                     # flat backdrop
    assert "IS_APPAREL||IS_BRANDED" in h or "IS_APPAREL || IS_BRANDED" in h
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Add the editor mode.** In listing_preview.py JS:
  - declare `let IS_BRANDED=false;` next to `let IS_APPAREL=false` (listing_preview.py:3284).
  - `function shopBranded(name,color){{ ...mirror shopApparel (listing_preview.py:3413): set product type to branded, set CURGARMENT=name, CURFMT=name+' - '+color, open the modal, applyProductChrome ... }}`. Reuse the apparel open path; where apparel uses `APPAREL_FORMATS`/`apparelFormatsFor`, branded uses `BRANDED_FORMATS` scoped by product name.
  - extend `setProductType(t)` (listing_preview.py:3376-3411) to accept `'branded'`: set `IS_BRANDED=(t==='branded')`, and for the shared apparel-style chrome treat branded like apparel where the behaviour is identical (movable frame, Layout Studio, colour swatches, print bound) by guarding those toggles on `IS_APPAREL||IS_BRANDED`.
  - in `applyProductChrome` (3346-3375), for branded swap the availability/about copy + step-3 label ("3. Size") + colour-row label ("Colour") + title, and SHOW `mlayoutbar`/`mframebar`/colour row; HIDE the front/back placement bar `mplacement` (branded is single-side in v1).
  - in `curFormats()`/format routing, route branded to `BRANDED_FORMATS`; in the print-bound code (`drawArt`, listing_preview.py:4819-4886) use `BRANDED_DIMS[product]` aspect for `_placeBoundMock` when `IS_BRANDED`.
  - backdrop: where `drawArt` calls `drawGarment` under `IS_APPAREL` (listing_preview.py ~4863), branch: `if(IS_BRANDED) _drawBrandedField(ctx,x,y,w,h); else if(IS_APPAREL) drawGarment(...)`. Add `function _drawBrandedField(ctx,x,y,w,h){{ ctx.save(); ctx.fillStyle='#f2efe9'; ctx.fillRect(x,y,w,h); ctx.strokeStyle='rgba(0,0,0,.10)'; ctx.strokeRect(x,y,w,h); ctx.restore(); }}` (a neutral product card; real product mockups are a later phase).
  - gate the Layout Studio draw + `_drawLayout` call on `IS_APPAREL||IS_BRANDED` (listing_preview.py:4886) and `renderLayoutGallery`/`renderSlotInputs` reveal in `applyProductChrome`.

- [ ] **Step 4: Rebuild + run the string test.** Expected: PASS.

- [ ] **Step 5: LIVE verify (Claude_Preview MCP).** Start `storefront`; `shopBranded("Organic Cotton Tote Bag","Natural")`; assert `IS_BRANDED===true`, the layout gallery shows, `pickLayout('badge')` + `onSlot('arcTop','ACME CO')` draws arc ink on the flat field (sample canvas pixels), colour swatch changes the field tone, and the final proof composes. Screenshot. Confirm no console errors.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_branded_storefront.py
git commit -m "feat(branded): editor mode reusing the print frame + Layout Studio"
```

---

## Task 9: Professional Higgsfield imagery

**Files:** Add `quoteforge/brand/dept-branded.jpg`, `quoteforge/brand/tile-<product_id>.jpg`

- [ ] **Step 1:** Generate a department hero + per-product tiles with the Higgsfield `generate_image` tool (marketing_studio model) using the prompts captured in the workflow output (clean studio flat-lays, neutral background, one abstract logo, NO real brand names). Generate hero + at least tote/bottle/tumbler/journal tiles.

- [ ] **Step 2:** Save into `quoteforge/brand/` as `dept-branded.jpg` and `tile-<product_id>.jpg` (the names `_branded_section`/data-prep already look up). Keep each ≤ ~200 KB; they are externalised by `_emit` like the apparel tiles.

- [ ] **Step 3:** `python -m quoteforge.admin rebuild-site`; confirm the tiles/hero appear (preview screenshot). These are owner-approved before launch.

- [ ] **Step 4: Commit**

```bash
git add quoteforge/brand/dept-branded.jpg quoteforge/brand/tile-*.jpg docs/index.html
git commit -m "feat(branded): professional department + product imagery"
```

---

## Task 10: Leak guard, full suite, safe-deploy

**Files:** Test `quoteforge_tests/test_branded_storefront.py`; full suite

- [ ] **Step 1: Add the leak guard test**

```python
def test_branded_no_supplier_leak(tmp_path):
    # REGRESSION: branded copy never exposes a print supplier.
    h = _page(tmp_path).lower()
    for bad in ("gelato", "printify", "printful"):
        assert bad not in h, bad
```

- [ ] **Step 2: Confirm the global guard passes.** Run `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_customer_copy_no_leak.py` → PASS (it scans the rebuilt page + `listing_preview.py` source; ensure the `brand=` Gelato blank names never reach the page — `_branded_section` must emit only name/colour/size/price).

- [ ] **Step 3: Full suite.** Run `python -m pytest -q --no-header -p no:cacheprovider`. Expected: all pass (prior count + new branded tests). Quote the real number.

- [ ] **Step 4: Safe-deploy loop.**

```bash
git push -u origin feat/branded-products-department
gh pr create --base main --title "feat: Custom Branded Products department (first pass)" --body-file <body>
git checkout main && git merge --no-ff feat/branded-products-department -m "Merge: Custom Branded Products department (first pass)" && git push origin main
python -m quoteforge.admin backup-all && python -m quoteforge.admin verify-backup   # RESULT: HEALTHY
```

- [ ] **Step 5: UAT.** Share `https://ajacobusa.github.io/members-reader/` (gate `Jesus`); note it reflects after the merge.

---

## Self-review notes

- **Spec coverage:** catalog/pricing (T1), Gelato ingest+guard (T2), pipeline wiring (T3), monitoring (T4), colours (T5), storefront section+data (T6), department chrome (T7), editor reuse + Layout Studio (T8), imagery (T9), leak guard + deploy (T10). Net-new (360 wrap, bundles, phone-case axis, pattern-tile) explicitly deferred per spec.
- **Naming consistency:** `BrandedProduct`, `BrandedVariant`, `BRANDED_CATALOG`, `build_branded_variations`, `branded_dimensions_for`, `get_product`, `_variant_sku`, `parse_branded_format`, `branded_sku_for`, `resolve_branded_sku`, `enrich_branded_order`, `verify_branded_mappings`; JS `IS_BRANDED`, `BRANDED_FORMATS`, `BRANDED_DIMS`, `shopBranded`, `_drawBrandedField` used consistently.
- **Verify-before-claim:** Tasks 3 and 4 begin with a `grep`/read to confirm the real apparel seam name/shape before mirroring — do not assume `audit_catalog`/call-site names; adapt to what is found.
- **Print-safety + leak guard** are pinned by tests in every storefront task.
