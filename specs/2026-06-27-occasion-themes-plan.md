# Subtle occasion themes — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open the storefront editor on an occasion-appropriate background+text colour (from the existing palette), flowing to the print, with the customer able to override.

**Architecture:** A Python source-of-truth table maps each occasion key (already embedded per product as `d.occ`) to a `{bg,text}` pair from the existing editor palette. The page embeds that table as `const OCCASION_TINT`; on editor-open the JS sets `SELBG`/`SELTXT` from `OCCASION_TINT[d.occ]`. `SELBG` only paints for wall-art (existing guard at `listing_preview.py:6854`), so v1 scope is automatic; the saved-design restore (`:6999`) and manual pickers override.

**Tech Stack:** Python 3.10+ (stdlib `json`), the generated storefront f-string in `listing_preview.py`, pytest. Run with `PYTHONNOUSERSITE=1 ./python/python.exe -m pytest`.

---

## File structure

- Create: `quoteforge/etsy/occasion_themes.py` — the occasion→tint table + `theme_for` + `tints_json`. Single responsibility: the mapping.
- Modify: `quoteforge/etsy/listing_preview.py` — embed `const OCCASION_TINT` (after `const DATA`) and apply it at editor-open (line 4156).
- Create: `quoteforge_tests/test_occasion_themes.py` — unit tests for the table + the embedded map + brand guard.

The occasion keys are exactly those returned by `_listing_occasion_key`
(`listing_preview.py:480-521`): `memorial, faith, anniversary, mother's day,
father's day, valentine's day, wedding, graduation, birthday, christmas, new baby,
housewarming, just because`, plus any `OCCASION_QUOTES` key.

---

### Task 1: occasion_themes module (table + resolver)

**Files:**
- Create: `quoteforge/etsy/occasion_themes.py`
- Test: `quoteforge_tests/test_occasion_themes.py`

- [ ] **Step 1: Write the failing test**

```python
# quoteforge_tests/test_occasion_themes.py
"""Subtle occasion themes: occasion key -> default {bg,text} from the EXISTING palette."""
import json

# the exact palette baked into the editor (listing_preview.py BGCOLORS / TXTCOLORS)
BGCOLORS = {"#103d2e", "#1b1b1f", "#3a2e24", "#7a2e2e", "#2e3a55", "#f4efe6", "#dcd6c8", "#c9a84c"}
TXTCOLORS = {"#f4efe6", "#ffffff", "#c9a84c", "#1b1b1f", "#103d2e", "#7a2e2e"}


def test_known_occasion_returns_its_pairing():
    from quoteforge.etsy.occasion_themes import theme_for
    assert theme_for("memorial") == {"bg": "#f4efe6", "text": "#103d2e"}
    assert theme_for("birthday") == {"bg": "#c9a84c", "text": "#1b1b1f"}
    assert theme_for("wedding") == {"bg": "#dcd6c8", "text": "#7a2e2e"}


def test_unknown_or_empty_returns_default():
    from quoteforge.etsy.occasion_themes import theme_for
    default = {"bg": "#103d2e", "text": "#f4efe6"}
    assert theme_for("just because") == default
    assert theme_for("") == default
    assert theme_for("not-an-occasion") == default


def test_every_tint_is_in_the_existing_palette():
    # brand guard: themes may NEVER introduce an off-palette colour
    from quoteforge.etsy.occasion_themes import OCCASION_TINTS, theme_for
    for t in list(OCCASION_TINTS.values()) + [theme_for("")]:
        assert t["bg"] in BGCOLORS and t["text"] in TXTCOLORS


def test_tints_json_round_trips():
    from quoteforge.etsy.occasion_themes import tints_json, OCCASION_TINTS
    assert json.loads(tints_json()) == OCCASION_TINTS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONNOUSERSITE=1 ./python/python.exe -m pytest -n0 quoteforge_tests/test_occasion_themes.py -q`
Expected: FAIL — `ModuleNotFoundError: quoteforge.etsy.occasion_themes`.

- [ ] **Step 3: Write minimal implementation**

```python
# quoteforge/etsy/occasion_themes.py
"""Subtle occasion themes: an occasion key -> a default {bg, text} colour for the
storefront editor, drawn ENTIRELY from the existing palette (BGCOLORS/TXTCOLORS in
listing_preview.py) so a theme can never introduce an off-brand colour. Applied as the
editor's STARTING colours; a saved design or any manual change overrides. Colour only
("Subtle") - the font is unchanged. Keys match listing_preview._listing_occasion_key.
"""
from __future__ import annotations

import json

_DEFAULT = {"bg": "#103d2e", "text": "#f4efe6"}   # today's default (deep green / cream)

OCCASION_TINTS: dict[str, dict] = {
    "memorial":        {"bg": "#f4efe6", "text": "#103d2e"},
    "faith":           {"bg": "#f4efe6", "text": "#103d2e"},
    "new baby":        {"bg": "#dcd6c8", "text": "#103d2e"},
    "housewarming":    {"bg": "#dcd6c8", "text": "#103d2e"},
    "mother's day":    {"bg": "#dcd6c8", "text": "#103d2e"},
    "wedding":         {"bg": "#dcd6c8", "text": "#7a2e2e"},
    "anniversary":     {"bg": "#dcd6c8", "text": "#7a2e2e"},
    "valentine's day": {"bg": "#dcd6c8", "text": "#7a2e2e"},
    "birthday":        {"bg": "#c9a84c", "text": "#1b1b1f"},
    "graduation":      {"bg": "#2e3a55", "text": "#f4efe6"},
    "father's day":    {"bg": "#2e3a55", "text": "#f4efe6"},
    "christmas":       {"bg": "#103d2e", "text": "#c9a84c"},
}


def theme_for(occ: str) -> dict:
    """The default {bg, text} for an occasion key; today's default for unknown/empty."""
    return OCCASION_TINTS.get((occ or "").strip().lower(), _DEFAULT)


def tints_json() -> str:
    """The occasion->tint map as compact JSON, for embedding in the storefront page."""
    return json.dumps(OCCASION_TINTS, separators=(",", ":"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONNOUSERSITE=1 ./python/python.exe -m pytest -n0 quoteforge_tests/test_occasion_themes.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/occasion_themes.py quoteforge_tests/test_occasion_themes.py
git commit -m "feat(themes): occasion -> default editor tint table (existing palette)"
```

---

### Task 2: embed the map + apply it at editor-open

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (3 edits: import, embed, apply)
- Test: `quoteforge_tests/test_occasion_themes.py` (add a build-time test)

- [ ] **Step 1: Write the failing test** (append to the test file)

```python
def _page(tmp_path):
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path, out_path=tmp_path / "h.html")
    return out.read_text(encoding="utf-8")


def test_page_embeds_tint_map_and_applies_it(tmp_path):
    html = _page(tmp_path)
    assert "const OCCASION_TINT = " in html                 # map embedded
    assert '"memorial":{"bg":"#f4efe6","text":"#103d2e"}' in html
    # editor-open applies the tint from the product's occasion key
    assert "OCCASION_TINT[d.occ]" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONNOUSERSITE=1 ./python/python.exe -m pytest -n0 quoteforge_tests/test_occasion_themes.py::test_page_embeds_tint_map_and_applies_it -q`
Expected: FAIL — `assert "const OCCASION_TINT = " in html` is False.

- [ ] **Step 3a: Import + compute the JSON (edit near `data_json = json.dumps(listings)`, line ~1758)**

Find:
```python
    data_json = json.dumps(listings)
```
Replace with:
```python
    data_json = json.dumps(listings)
    from quoteforge.etsy.occasion_themes import tints_json
    occ_tint_json = tints_json()
```

- [ ] **Step 3b: Embed the map (edit `const DATA = {data_json};`, line ~3963)**

Find:
```
 const DATA = {data_json};
```
Replace with:
```
 const DATA = {data_json};
 const OCCASION_TINT = {occ_tint_json};
```
(Single braces = f-string interpolation, exactly like `data_json`.)

- [ ] **Step 3c: Apply at editor-open (edit line ~4156)**

Find:
```
   CURQUOTE = d.quote || ""; SELBG = BGCOLORS[0]; SELTXT = TXTCOLORS[0]; TXT_USER_SET=false; APPLACEMENT='front';
```
Replace with (note doubled braces — this is inside the page f-string):
```
   CURQUOTE = d.quote || ""; SELBG = BGCOLORS[0]; SELTXT = TXTCOLORS[0]; TXT_USER_SET=false; APPLACEMENT='front';
   var _ot=(typeof OCCASION_TINT!=='undefined'&&d.occ)?OCCASION_TINT[d.occ]:null; if(_ot){{SELBG=_ot.bg; SELTXT=_ot.text;}}
```
No wall-art guard is needed: `SELBG` only paints for wall-art (`listing_preview.py:6854`), and the saved-design restore (`:6999 if(s.bg)SELBG=s.bg`) plus the manual `pickBg` (`:5987`) run later and override.

- [ ] **Step 4: Run test + rebuild + verify**

Run: `PYTHONNOUSERSITE=1 ./python/python.exe -m pytest -n0 quoteforge_tests/test_occasion_themes.py -q`
Expected: PASS (5 passed).

Run: `PYTHONNOUSERSITE=1 ./python/python.exe -m quoteforge.admin rebuild-site`
Then confirm the regenerated page carries the map:
Run (Grep tool, not shell): pattern `const OCCASION_TINT = ` in `docs/index.html` — count must be > 0.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/listing_preview.py quoteforge_tests/test_occasion_themes.py docs/index.html docs/app.js
git commit -m "feat(themes): apply occasion tint as the editor's starting colours"
```

---

### Task 3: full-suite green + source integrity

**Files:** none (verification task)

- [ ] **Step 1: Source integrity (byte-compiles the page f-string + imports)**

Run: `PYTHONNOUSERSITE=1 ./python/python.exe -m pytest -n0 quoteforge_tests/test_source_integrity.py -q`
Expected: PASS.

- [ ] **Step 2: Full suite**

Run: `PYTHONNOUSERSITE=1 ./python/python.exe -m pytest -q --no-header -p no:cacheprovider`
Expected: all pass, 0 failed (quote the real count).

- [ ] **Step 3: PR + merge + backup (standard loop)**

```bash
git push -u origin feat/occasion-themes
gh pr create --base main --title "Subtle occasion themes (editor starting tint per occasion)" --body "..."
git checkout main && git merge --no-ff feat/occasion-themes && git push origin main
PYTHONNOUSERSITE=1 ./python/python.exe -m quoteforge.admin backup-all
PYTHONNOUSERSITE=1 ./python/python.exe -m quoteforge.admin verify-backup
```

Then give the UAT link `https://ajacobusa.github.io/members-reader/` (gate `Jesus`), noting it reflects once GitHub Pages rebuilds.

---

## Self-review

- **Spec coverage:** table (Task 1) ✓; mood/occasion resolution via `d.occ` (already embedded) ✓; editor init from default (Task 2) ✓; print flows via canvas (no code — `exportPrint` already renders `SELBG`) ✓; override wins (existing `:6999`/`:5987`, no code) ✓; wall-art-only scope (existing `:6854`, no code) ✓; brand guard (Task 1 test) ✓; unknown→default (Task 1 test) ✓.
- **Placeholder scan:** all code is concrete; the only `"..."` is the PR body, written at PR time.
- **Type consistency:** `theme_for`/`tints_json`/`OCCASION_TINTS` names match across module, tests, and the embed; JS reads `OCCASION_TINT[d.occ].bg/.text` matching the dict shape.
