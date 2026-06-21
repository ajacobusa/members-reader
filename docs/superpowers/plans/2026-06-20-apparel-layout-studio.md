# Apparel Layout Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an apparel customer upload a logo + type words, pick one of 12 professional preset layouts (incl. curved/arc badge styles), and get an auto-arranged, fully tweakable print-ready design.

**Architecture:** All in the storefront generator `quoteforge/etsy/listing_preview.py` (a brace-escaped page f-string: `{{ }}` = literal JS braces, `${{ }}` = JS template interp). A new curved-text canvas routine + a data-driven `LAYOUTS` table drive a new "layout mode" branch in `drawArt()`. Structured text **slots** feed each layout. A gallery UI picks layouts; Freeform stays the untouched default. Per-side state (`SIDES`) and the order payload carry the chosen layout + slots. The proof + front/back-rotate pipeline is unchanged (it composites whatever `drawArt()` renders).

**Tech Stack:** Python (page generator) emitting HTML/CSS/Canvas-2D JS. Google Fonts. Pytest string/integration tests over the generated `docs/index.html`. Claude_Preview MCP for live canvas verification.

**Reference spec:** `docs/superpowers/specs/2026-06-20-apparel-layout-studio-design.md`

**Conventions for every task:**
- After editing the f-string, regenerate: `python -m quoteforge.admin rebuild-site`, then assert on the regenerated `docs/index.html` (tests call `_page(tmp_path)` which builds its own copy).
- Tests live in `quoteforge_tests/test_apparel_storefront.py`; reuse its `_page(tmp_path)` helper.
- Targeted test run: `python -m pytest -q --no-header -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py`.
- Source-integrity net after f-string edits: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_source_integrity.py`.
- Each `# REGRESSION:`-tagged test names the behaviour it pins.
- Hard rule: no supplier/marketplace names (Gelato/Printify/Etsy) anywhere, incl. JS identifiers/comments.

---

## File structure

Single file changes (storefront): `quoteforge/etsy/listing_preview.py`
- Head `<link>` (line ~1563): add display fonts.
- JS `FONTS` (line ~3246): add font entries.
- JS new globals + functions: `drawArcText`, `LAYOUTS`, `SLOTS`, `CURLAYOUT`, decor helpers, gallery/slot UI functions.
- `drawArt()` (line ~4571): add the apparel layout branch.
- `_captureSide`/`_restoreSide` (line ~4209): persist `CURLAYOUT` + `SLOTS`.
- Cart/order payload (lines ~3516, ~3754, ~4725/4741): carry layout + slot text; set `wording` to a readable slot concat.
- Editor controls column (after `#mframebar`, line ~2818): the Layout gallery + slot inputs panel.

Tests: `quoteforge_tests/test_apparel_storefront.py` (new test fns).

---

## Task 1: Add display fonts

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py:1563` (font `<link>`), `:3246` (`FONTS`)
- Test: `quoteforge_tests/test_apparel_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_display_fonts_loaded(tmp_path):
    # REGRESSION: Layout Studio needs bold display fonts (Bebas Neue for
    # streetwear/athletic, Oswald weights) loaded and offered in the font picker.
    h = _page(tmp_path)
    assert "Bebas+Neue" in h                      # loaded via Google Fonts
    assert "family=Oswald:wght@500;600;700" in h or "Oswald:wght@500;600;700" in h
    assert "'Bebas Neue'" in h                     # present in the FONTS picker list
    assert "Oswald" in h
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_display_fonts_loaded`
Expected: FAIL (`Bebas+Neue` not in page).

- [ ] **Step 3: Add the fonts to the `<link>` (line ~1563)**

Replace the existing second font link's family list so it includes Bebas Neue and Oswald weights:

```
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Montserrat:wght@400;600&family=Lora:wght@400;600&family=Dancing+Script:wght@600;700&family=Oswald:wght@500;600;700&family=Bebas+Neue&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
```

- [ ] **Step 4: Add to `FONTS` (line ~3246)**

Append two entries to the `FONTS` array (keep existing entries):

```
   ["Bebas","'Bebas Neue',sans-serif"],
   ["Oswald","'Oswald',sans-serif"]];
```

(Insert before the closing `]` of the FONTS literal; keep the existing fonts.)

- [ ] **Step 5: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_display_fonts_loaded`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): add Bebas Neue + Oswald display fonts for layout studio"
```

---

## Task 2: Curved-text engine `drawArcText`

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (add fn near `drawGarment`/`drawArt`, e.g. after `_isLight` ~line 4575)
- Test: `quoteforge_tests/test_apparel_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_arc_text_engine(tmp_path):
    # REGRESSION: the curved-text engine that arcs wording around the logo.
    h = _page(tmp_path)
    assert "function drawArcText" in h
    assert "measureText" in h                      # advances angle by glyph width
    assert "sweep" in h                            # top vs bottom arc direction
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_arc_text_engine`
Expected: FAIL.

- [ ] **Step 3: Implement `drawArcText` (escaped for the f-string)**

Insert this JS (note `{{`/`}}` escaping) near the other canvas helpers:

```
 // Draw `text` along a circle centred (cx,cy), radius r, centred on midDeg.
 // sweep=+1 -> top arc (reads clockwise, glyphs upright outside the ring);
 // sweep=-1 -> bottom arc (glyphs rotated 180 so they read upright below).
 function drawArcText(ctx,text,cx,cy,r,midDeg,sweep,font,size,color,ls){{
   text=(text||'').toString(); if(!text) return;
   ls=ls||0;
   ctx.save(); ctx.fillStyle=color; ctx.textAlign='center'; ctx.textBaseline='middle';
   ctx.font='700 '+size+'px '+font;
   var widths=[],total=0;
   for(var i=0;i<text.length;i++){{ var w=ctx.measureText(text[i]).width+ls; widths.push(w); total+=w; }}
   var totalAngle=total/r;                        // radians the word subtends
   var a=(midDeg*Math.PI/180) - sweep*totalAngle/2;
   for(var j=0;j<text.length;j++){{
     var aw=widths[j]/r; a+=sweep*aw/2;
     var x=cx+Math.cos(a)*r, y=cy+Math.sin(a)*r;
     ctx.save(); ctx.translate(x,y);
     ctx.rotate(a + (sweep>0?Math.PI/2:-Math.PI/2));
     ctx.fillText(text[j],0,0); ctx.restore();
     a+=sweep*aw/2;
   }}
   ctx.restore();
 }}
```

- [ ] **Step 4: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_arc_text_engine`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): curved-text engine (drawArcText) for badge layouts"
```

---

## Task 3: Slots state, CURLAYOUT, and the LAYOUTS table (Freeform + Circular Badge)

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (new JS globals near `APPLACEMENT` ~line 4141; LAYOUTS near `APPARELCOLOR` ~line 4394)
- Test: `quoteforge_tests/test_apparel_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_state_and_first_layouts(tmp_path):
    # REGRESSION: layout state + the data-driven LAYOUTS table; Freeform default
    # plus the hero Circular Badge with top/bottom arc slots.
    h = _page(tmp_path)
    assert "const LAYOUTS" in h
    assert "let CURLAYOUT" in h and "'freeform'" in h        # freeform default
    assert "let SLOTS" in h
    for slot in ("headline","secondary","arcTop","arcBottom","tagline","monogram"):
        assert slot in h, slot
    assert "Circular Badge" in h                              # hero layout present
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_state_and_first_layouts`
Expected: FAIL.

- [ ] **Step 3: Add state globals (near `let APPLACEMENT='front';` ~line 4141)**

```
 let CURLAYOUT='freeform';   // selected apparel layout preset ('freeform' = manual)
 let SLOTS={{headline:'',secondary:'',arcTop:'',arcBottom:'',tagline:'',monogram:''}};
 function _slot(k){{ return (SLOTS&&SLOTS[k])||''; }}
```

- [ ] **Step 4: Add the LAYOUTS table (after `APPARELCOLOR` ~line 4394)**

Start with Freeform + Circular Badge (more added in Task 6). Positions are FRACTIONS of the print bound `b={{x,y,w,h}}` resolved at draw time.

```
 // Data-driven apparel layouts. Each slot: kind 'arc'|'line', position as a
 // fraction of the print bound, size weight, font, caps. logo.frame draws a
 // decoration. r/midAngle/sweep are for arcs (sweep +1 top, -1 bottom).
 const LAYOUTS=[
  {{key:'freeform',name:'Freeform'}},
  {{key:'badge',name:'Circular Badge',logo:{{cx:0.5,cy:0.5,scale:0.42,frame:'doublering'}},
    decor:['waves'],defaultFont:"'Oswald',sans-serif",
    slots:[
     {{slot:'arcTop',kind:'arc',cx:0.5,cy:0.5,r:0.40,midAngle:-90,sweep:1,weight:0.085,caps:true}},
     {{slot:'arcBottom',kind:'arc',cx:0.5,cy:0.5,r:0.40,midAngle:90,sweep:-1,weight:0.06,caps:true}}
    ]}}
 ];
 function _layout(k){{ for(var i=0;i<LAYOUTS.length;i++) if(LAYOUTS[i].key===k) return LAYOUTS[i]; return LAYOUTS[0]; }}
```

- [ ] **Step 5: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_state_and_first_layouts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): layout state + LAYOUTS table (freeform + circular badge)"
```

---

## Task 4: `drawArt()` layout-mode branch

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (`drawArt` ~line 4571, in the apparel block after the print bound `b` is computed)
- Test: `quoteforge_tests/test_apparel_storefront.py` + live pixel check

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_drawart_branch(tmp_path):
    # REGRESSION: drawArt renders a chosen layout (decor -> logo -> slots) instead
    # of the single text block; freeform keeps today's path.
    h = _page(tmp_path)
    assert "_drawLayout(" in h                       # layout renderer invoked
    assert "CURLAYOUT!=='freeform'" in h             # gated; freeform unchanged
    assert "function _drawLayout" in h
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_drawart_branch`
Expected: FAIL.

- [ ] **Step 3: Add `_drawLayout` and call it from `drawArt`**

In `drawArt`, locate the apparel block where the print bound is computed (`APPAREL_BOUND=b;` after `_placeBoundMock`/`_placeBound`). After the photo is drawn for apparel, branch: if a non-freeform layout is selected, call `_drawLayout` and SKIP the single-text-block render. Concretely, guard the existing wording render with `if(!IS_APPAREL || CURLAYOUT==='freeform')` and add, in the apparel path:

```
   if(IS_APPAREL && CURLAYOUT!=='freeform'){{ _drawLayout(ctx,APPAREL_BOUND); }}
```

Add the renderer (escaped):

```
 // Render the selected layout inside print bound b={{x,y,w,h}}. Order: decor,
 // (logo already composited by drawArt as PHOTO), then text slots (arc or line).
 function _drawLayout(ctx,b){{
   const L=_layout(CURLAYOUT); if(!L||L.key==='freeform') return;
   const cx=b.x+b.w/2, cy=b.y+b.h/2, R=Math.min(b.w,b.h);
   const ink=SELTXT||'#1c1c1e', font=L.defaultFont||SELFONT;
   (L.decor||[]).forEach(function(d){{ _decor(ctx,d,b,ink); }});
   (L.slots||[]).forEach(function(s){{
     var txt=_slot(s.slot); if(!txt) return;
     var size=Math.max(11, R*(s.weight||0.07));
     var t=s.caps?txt.toUpperCase():txt;
     if(s.kind==='arc'){{
       drawArcText(ctx,t, b.x+b.w*s.cx, b.y+b.h*s.cy, R*s.r, s.midAngle, s.sweep, font, size, ink, size*0.06);
     }} else {{
       ctx.save(); ctx.fillStyle=ink; ctx.font='700 '+size+'px '+font;
       ctx.textAlign=s.align||'center'; ctx.textBaseline='middle';
       var ax=(s.align==='left')?b.x+b.w*s.x:(s.align==='right')?b.x+b.w*s.x:b.x+b.w*(s.x==null?0.5:s.x);
       ctx.fillText(t, ax, b.y+b.h*s.y); ctx.restore();
     }}
   }});
 }}
```

Note: `_decor` is added in Task 5; until then add a temporary stub `function _decor(){{}}` so the page is valid, and remove it in Task 5. (Add the stub now.)

- [ ] **Step 4: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_drawart_branch quoteforge_tests/test_source_integrity.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): drawArt layout-mode branch (_drawLayout)"
```

---

## Task 5: Decorative element helpers

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (replace the `_decor` stub with the real dispatcher + helpers)
- Test: `quoteforge_tests/test_apparel_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_decor_helpers(tmp_path):
    # REGRESSION: decorative elements layouts can drop in (ring, banner, waves,
    # shield/hexagon, rule, stars, monogram frame, collage frames).
    h = _page(tmp_path)
    assert "function _decor" in h
    for d in ("ring","doublering","banner","waves","shield","hexagon","rule","stars","monogram","collage"):
        assert "'"+d+"'" in h, d
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_decor_helpers`
Expected: FAIL (stub has no cases).

- [ ] **Step 3: Replace the `_decor` stub with the dispatcher + shapes**

```
 // Decorations drawn in ink inside bound b. Kept simple + print-safe.
 function _decor(ctx,kind,b,ink){{
   const cx=b.x+b.w/2, cy=b.y+b.h/2, R=Math.min(b.w,b.h);
   ctx.save(); ctx.strokeStyle=ink; ctx.fillStyle=ink; ctx.lineWidth=Math.max(2,R*0.012);
   if(kind==='ring'){{ ctx.beginPath(); ctx.arc(cx,cy,R*0.47,0,7); ctx.stroke(); }}
   else if(kind==='doublering'){{ ctx.beginPath(); ctx.arc(cx,cy,R*0.47,0,7); ctx.stroke();
     ctx.lineWidth=Math.max(1,R*0.006); ctx.beginPath(); ctx.arc(cx,cy,R*0.42,0,7); ctx.stroke(); }}
   else if(kind==='border'){{ ctx.strokeRect(b.x+b.w*0.06,b.y+b.h*0.06,b.w*0.88,b.h*0.88); }}
   else if(kind==='rule'){{ ctx.beginPath(); ctx.moveTo(b.x+b.w*0.3,cy); ctx.lineTo(b.x+b.w*0.7,cy); ctx.stroke(); }}
   else if(kind==='waves'){{ ctx.lineWidth=Math.max(2,R*0.01);
     for(var k=0;k<2;k++){{ var yy=cy+R*(0.14+k*0.07); ctx.beginPath();
       for(var x=b.x+b.w*0.30;x<=b.x+b.w*0.70;x+=2){{ var yo=Math.sin((x-b.x)/ (b.w*0.05))*R*0.02;
         (x===b.x+b.w*0.30)?ctx.moveTo(x,yy+yo):ctx.lineTo(x,yy+yo); }} ctx.stroke(); }} }}
   else if(kind==='banner'){{ var bw=b.w*0.5,bh=b.h*0.12,bx=cx-bw/2,by=cy+R*0.18;
     ctx.fillRect(bx,by,bw,bh); }}
   else if(kind==='shield'){{ ctx.beginPath();
     ctx.moveTo(cx,b.y+b.h*0.12); ctx.lineTo(b.x+b.w*0.82,b.y+b.h*0.30);
     ctx.lineTo(b.x+b.w*0.82,b.y+b.h*0.62); ctx.lineTo(cx,b.y+b.h*0.88);
     ctx.lineTo(b.x+b.w*0.18,b.y+b.h*0.62); ctx.lineTo(b.x+b.w*0.18,b.y+b.h*0.30);
     ctx.closePath(); ctx.stroke(); }}
   else if(kind==='hexagon'){{ ctx.beginPath();
     for(var i=0;i<6;i++){{ var a=Math.PI/180*(60*i-90), px=cx+Math.cos(a)*R*0.46, py=cy+Math.sin(a)*R*0.46;
       i?ctx.lineTo(px,py):ctx.moveTo(px,py); }} ctx.closePath(); ctx.stroke(); }}
   else if(kind==='stars'){{ for(var s=-1;s<=1;s++){{ _star(ctx,cx+s*R*0.16,cy+R*0.30,R*0.03,ink); }} }}
   else if(kind==='monogram'){{ ctx.beginPath(); ctx.arc(cx,cy,R*0.34,0,7); ctx.stroke(); }}
   else if(kind==='collage'){{ var g=R*0.02;
     [[0,0],[1,0],[0,1],[1,1]].forEach(function(p){{ ctx.strokeRect(
       (p[0]?cx+g:b.x+b.w*0.10), (p[1]?cy+g:b.y+b.h*0.10), b.w*0.40-g, b.h*0.40-g); }}); }}
   ctx.restore();
 }}
 function _star(ctx,cx,cy,r,ink){{ ctx.save(); ctx.fillStyle=ink; ctx.beginPath();
   for(var i=0;i<10;i++){{ var rr=i%2?r*0.45:r, a=Math.PI/180*(36*i-90);
     var x=cx+Math.cos(a)*rr, y=cy+Math.sin(a)*rr; i?ctx.lineTo(x,y):ctx.moveTo(x,y); }}
   ctx.closePath(); ctx.fill(); ctx.restore(); }}
```

(Delete the temporary `function _decor(){{}}` stub from Task 4.)

- [ ] **Step 4: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_decor_helpers quoteforge_tests/test_source_integrity.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): decorative element helpers for layouts"
```

---

## Task 6: Remaining layouts (B–L data)

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (extend the `LAYOUTS` array)
- Test: `quoteforge_tests/test_apparel_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_all_twelve_layouts(tmp_path):
    # REGRESSION: all 12 named layouts present (+ freeform).
    h = _page(tmp_path)
    names = ["Circular Badge","Vintage Emblem","Modern Minimalist","Oversized Streetwear",
             "Vertical Stack","Horizontal Banner","Left-Chest Logo","Back Print",
             "Wraparound","Photo Collage","Adventure Badge","Luxury Monogram"]
    for n in names:
        assert n in h, n
    # arc layouts use the engine; emblem/adventure use shaped frames
    for k in ("badge","emblem","minimal","street","vstack","hbanner","chest","backprint",
              "wrap","collage","adventure","monogram"):
        assert "'"+k+"'" in h, k
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_all_twelve_layouts`
Expected: FAIL.

- [ ] **Step 3: Append B–L to `LAYOUTS`**

Add these entries to the `LAYOUTS` array (after `badge`). Coordinates are fractions of the print bound; `weight` is fraction of `min(w,h)` for font size.

```
  ,{{key:'emblem',name:'Vintage Emblem',logo:{{cx:0.5,cy:0.46,scale:0.34,frame:'border'}},
    decor:['border','banner'],defaultFont:"'Cormorant Garamond',serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.16,weight:0.10,caps:true}},
           {{slot:'secondary',kind:'line',x:0.5,y:0.74,weight:0.055,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.88,weight:0.04,caps:true}}]}}
  ,{{key:'minimal',name:'Modern Minimalist',logo:{{cx:0.5,cy:0.36,scale:0.24,frame:'none'}},
    decor:['rule'],defaultFont:"'Montserrat',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.60,weight:0.08,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.74,weight:0.035,caps:true}}]}}
  ,{{key:'street',name:'Oversized Streetwear',logo:{{cx:0.5,cy:0.46,scale:0.62,frame:'none'}},
    decor:[],defaultFont:"'Bebas Neue',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.60,weight:0.20,caps:true}},
           {{slot:'secondary',kind:'line',x:0.5,y:0.80,weight:0.07,caps:true}}]}}
  ,{{key:'vstack',name:'Vertical Stack',logo:{{cx:0.5,cy:0.5,scale:0.34,frame:'none'}},
    decor:['rule'],defaultFont:"'Bebas Neue',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.18,weight:0.12,caps:true}},
           {{slot:'secondary',kind:'line',x:0.5,y:0.80,weight:0.06,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.90,weight:0.04,caps:true}}]}}
  ,{{key:'hbanner',name:'Horizontal Banner',logo:{{cx:0.28,cy:0.5,scale:0.30,frame:'none'}},
    decor:[],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.62,y:0.44,weight:0.10,align:'center',caps:true}},
           {{slot:'secondary',kind:'line',x:0.62,y:0.58,weight:0.05,align:'center',caps:true}}]}}
  ,{{key:'chest',name:'Left-Chest Logo',logo:{{cx:0.32,cy:0.34,scale:0.18,frame:'none'}},
    decor:[],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.32,y:0.46,weight:0.04,caps:true}}]}}
  ,{{key:'backprint',name:'Back Print',logo:{{cx:0.5,cy:0.55,scale:0.5,frame:'none'}},
    decor:[],defaultFont:"'Bebas Neue',sans-serif",
    slots:[{{slot:'arcTop',kind:'arc',cx:0.5,cy:0.40,r:0.34,midAngle:-90,sweep:1,weight:0.07,caps:true}},
           {{slot:'tagline',kind:'line',x:0.5,y:0.88,weight:0.07,caps:true}}]}}
  ,{{key:'wrap',name:'Wraparound',logo:{{cx:0.5,cy:0.5,scale:0.46,frame:'none'}},
    decor:[],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'arcTop',kind:'arc',cx:0.5,cy:0.5,r:0.46,midAngle:-90,sweep:1,weight:0.055,caps:true}}]}}
  ,{{key:'collage',name:'Photo Collage',logo:{{cx:0.5,cy:0.46,scale:0.22,frame:'none'}},
    decor:['collage'],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'headline',kind:'line',x:0.5,y:0.92,weight:0.06,caps:true}}]}}
  ,{{key:'adventure',name:'Adventure Badge',logo:{{cx:0.5,cy:0.5,scale:0.30,frame:'shield'}},
    decor:['shield'],defaultFont:"'Oswald',sans-serif",
    slots:[{{slot:'arcTop',kind:'arc',cx:0.5,cy:0.5,r:0.33,midAngle:-90,sweep:1,weight:0.06,caps:true}},
           {{slot:'arcBottom',kind:'arc',cx:0.5,cy:0.5,r:0.33,midAngle:90,sweep:-1,weight:0.05,caps:true}}]}}
  ,{{key:'monogram',name:'Luxury Monogram',logo:{{cx:0.5,cy:0.42,scale:0.0,frame:'monogram'}},
    decor:['monogram'],defaultFont:"'Cormorant Garamond',serif",
    slots:[{{slot:'monogram',kind:'line',x:0.5,y:0.42,weight:0.26,caps:true}},
           {{slot:'headline',kind:'line',x:0.5,y:0.74,weight:0.05,caps:true}}]}}
```

- [ ] **Step 4: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_all_twelve_layouts quoteforge_tests/test_source_integrity.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): add the remaining 11 preset layouts"
```

---

## Task 7: Layout gallery UI + slot inputs

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (HTML panel after `#mframebar` ~line 2818; CSS near the editor styles; JS `renderLayoutGallery`, `pickLayout`, `renderSlotInputs`, `onSlot`)
- Test: `quoteforge_tests/test_apparel_storefront.py` + live verify

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_gallery_ui(tmp_path):
    # REGRESSION: the editor exposes a Layout gallery (Freeform + 12 thumbs) and
    # swaps the visible text-slot inputs when a layout is chosen.
    h = _page(tmp_path)
    assert 'id="mlayouts"' in h                       # gallery container
    assert "function renderLayoutGallery" in h
    assert "function pickLayout" in h
    assert "function renderSlotInputs" in h            # swaps inputs per layout
    assert "onSlot(" in h                              # slot input handler
    assert "renderLayoutGallery()" in h                # invoked on editor open
    assert h.count("layoutthumb") >= 12                # a thumbnail per layout
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_gallery_ui`
Expected: FAIL.

- [ ] **Step 3: Add the HTML panel (after the `#mframebar` dragbar ~line 2818)**

```
       <div class="dragbar" id="mlayoutbar" style="display:none">
         <div class="dbq">&#127912; Pick a <b>layout</b> &mdash; we arrange your logo &amp; words professionally. Tweak anything after.</div>
         <div id="mlayouts" class="layoutgrid"></div>
         <div id="mslots" class="slotinputs"></div>
       </div>
```

- [ ] **Step 4: Add CSS (near the editor `.dragbar`/`.fonts` styles)**

```
 .layoutgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(64px,1fr));gap:6px;margin:6px 0}}
 .layoutthumb{{border:1px solid var(--line);border-radius:8px;padding:3px;background:#fff;cursor:pointer}}
 .layoutthumb.sel{{outline:2px solid var(--green);outline-offset:1px}}
 .layoutthumb svg{{width:100%;height:auto;display:block}}
 .layoutthumb span{{display:block;font-size:9px;text-align:center;color:#5b6b62;margin-top:2px}}
 .slotinputs label{{display:block;font-size:12px;margin:6px 0 2px;color:#3a4a42}}
 .slotinputs input{{width:100%;padding:7px;border:1px solid var(--line);border-radius:8px;font-size:13px}}
```

- [ ] **Step 5: Add the JS (gallery, pick, slot inputs)**

`SLOT_LABELS` maps slot keys to customer-facing labels. `renderLayoutGallery` builds a thumbnail per `LAYOUTS` entry (reuse small inline SVGs — a simplified emblem + arcs; the exact thumb markup can mirror the design mock). `pickLayout` sets `CURLAYOUT`, re-renders slot inputs + gallery selection, redraws. `renderSlotInputs` shows only the active layout's slots; `onSlot` writes into `SLOTS` and redraws. For the `freeform` thumb, selecting it hides slot inputs and shows the existing single text box.

```
 const SLOT_LABELS={{headline:'Main words',secondary:'Second line',arcTop:'Top curved line',
   arcBottom:'Bottom curved line',tagline:'Small line (date / place)',monogram:'Initials'}};
 function _thumbSVG(L){{
   if(L.key==='freeform') return '<svg viewBox="0 0 60 60"><rect x="6" y="22" width="48" height="6" rx="2" fill="#c9d6cd"/><rect x="14" y="32" width="32" height="5" rx="2" fill="#dfe6e1"/></svg>';
   var arcs=(L.slots||[]).some(function(s){{return s.kind==='arc';}});
   var emb='<path d="M22,38 L30,24 L34,31 L40,21 L46,38 Z" fill="#1c1c1e"/>';
   var top=arcs?'<path id="t'+L.key+'" d="M14,30 A16,16 0 0 1 46,30" fill="none"/><text font-size="7" fill="#1c1c1e"><textPath href="#t'+L.key+'" startOffset="50%" text-anchor="middle">ABC</textPath></text>':'';
   return '<svg viewBox="0 0 60 60">'+top+emb+'</svg>';
 }}
 function renderLayoutGallery(){{
   var box=document.getElementById('mlayouts'); if(!box) return;
   box.innerHTML=LAYOUTS.map(function(L){{
     return '<div class="layoutthumb'+(L.key===CURLAYOUT?' sel':'')+'" role="button" tabindex="0" '+
       'onclick="pickLayout(\\''+L.key+'\\')" onkeydown="if(event.key===\\'Enter\\')pickLayout(\\''+L.key+'\\')" '+
       'title="'+L.name+'">'+_thumbSVG(L)+'<span>'+L.name+'</span></div>';
   }}).join('');
 }}
 function renderSlotInputs(){{
   var box=document.getElementById('mslots'); if(!box) return;
   var L=_layout(CURLAYOUT);
   var keys=(L.slots||[]).map(function(s){{return s.slot;}});
   var uniq=keys.filter(function(k,i){{return keys.indexOf(k)===i;}});
   box.innerHTML=uniq.map(function(k){{
     return '<label>'+SLOT_LABELS[k]+'</label><input id="slot_'+k+'" maxlength="40" value="'+
       (_slot(k).replace(/"/g,'&quot;'))+'" oninput="onSlot(\\''+k+'\\',this.value)">';
   }}).join('');
   // Freeform uses the existing #mtext box; layouts hide it.
   var tw=document.getElementById('mtextwrap'); if(tw) tw.style.display=(CURLAYOUT==='freeform')?'':'none';
 }}
 function onSlot(k,v){{ SLOTS[k]=v; if(k==='headline'){{ var ta=document.getElementById('mtext'); if(ta) ta.value=v; }} drawArt(); }}
 function pickLayout(k){{ CURLAYOUT=k; renderLayoutGallery(); renderSlotInputs(); drawArt(); }}
```

Note: if the existing text box has no `#mtextwrap` wrapper, wrap the `<textarea id="mtext">` and its label in `<div id="mtextwrap">...</div>` so layouts can hide it. Show `#mlayoutbar` for apparel only — in the function that reveals apparel controls (where `#mplacement`/`#mframebar` are shown), also set `#mlayoutbar` display to block and call `renderLayoutGallery(); renderSlotInputs();`.

- [ ] **Step 6: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_gallery_ui quoteforge_tests/test_source_integrity.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): layout gallery UI + per-layout slot inputs"
```

---

## Task 8: Per-side persistence + order payload

**Files:**
- Modify: `quoteforge/etsy/listing_preview.py` (`_captureSide`/`_restoreSide` ~line 4209; cart payload ~3516/3754; order summary ~4725/4741)
- Test: `quoteforge_tests/test_apparel_storefront.py`

- [ ] **Step 1: Write the failing test**

```python
def test_layout_studio_persists_and_payload(tmp_path):
    # REGRESSION: layout + slots persist per side and reach the order payload;
    # `wording` is set to a readable concat of the active slots.
    h = _page(tmp_path)
    assert "layout:CURLAYOUT" in h or "layout: CURLAYOUT" in h     # captured per side
    assert "slots:" in h                                            # slot text snapshot
    assert "function _slotWording" in h                            # readable concat
    assert "_slotWording(" in h                                     # used in payload
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_persists_and_payload`
Expected: FAIL.

- [ ] **Step 3: Persist in `_captureSide` / `_restoreSide`**

In `_captureSide` return object, add: `layout:CURLAYOUT, slots:JSON.parse(JSON.stringify(SLOTS))`.
In `_restoreSide(s)`, restore: `CURLAYOUT=(s&&s.layout)||'freeform'; SLOTS=(s&&s.slots)?JSON.parse(JSON.stringify(s.slots)):{{headline:'',secondary:'',arcTop:'',arcBottom:'',tagline:'',monogram:''}};` and after restoring call `renderLayoutGallery(); renderSlotInputs();`. In the empty-side branch reset both to freeform/empty.

- [ ] **Step 4: Add `_slotWording` and use it in the payload**

```
 // Human-readable wording from the active layout's slots (for summaries + print).
 function _slotWording(){{
   if(CURLAYOUT==='freeform') return ((document.getElementById('mtext')||{{}}).value||'');
   var L=_layout(CURLAYOUT), seen={{}}, out=[];
   (L.slots||[]).forEach(function(s){{ var v=_slot(s.slot);
     if(v && !seen[s.slot]){{ seen[s.slot]=1; out.push(v); }} }});
   return out.join(' / ');
 }}
```

In the cart snapshot (~line 3754) and order-item builder (~4725), replace the `wording` source `((document.getElementById('mtext')||{{}}).value||'')` with `_slotWording()`, and add `layout:CURLAYOUT` to the stored item so production has the composition name.

- [ ] **Step 5: Rebuild + run test**

Run: `python -m quoteforge.admin rebuild-site && python -m pytest -q -p no:cacheprovider quoteforge_tests/test_apparel_storefront.py::test_layout_studio_persists_and_payload quoteforge_tests/test_source_integrity.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add quoteforge/etsy/listing_preview.py docs/index.html quoteforge_tests/test_apparel_storefront.py
git commit -m "feat(editor): persist layout+slots per side and carry into the order payload"
```

---

## Task 9: No-leak guard, full suite, live verify, deploy

**Files:**
- Test: `quoteforge_tests/test_apparel_storefront.py`, full suite

- [ ] **Step 1: Add a leak guard test**

```python
def test_layout_studio_no_supplier_leak(tmp_path):
    # REGRESSION: layout names + help text never expose a supplier/marketplace.
    h = _page(tmp_path).lower()
    for bad in ("gelato","printify","printful","etsy"):
        assert bad not in h, bad
```

(If `test_customer_copy_no_leak.py` already scans the page, confirm it still passes instead of duplicating.)

- [ ] **Step 2: Live verification (Claude_Preview MCP)**

Start the `storefront` preview. In the editor for "Men's T-Shirt", set `SLOTS.arcTop="CAMP WINDERMERE"`, `SLOTS.arcBottom="LAKE MARTIN 2025"`, `pickLayout('badge')`, `drawArt()`. Sample canvas pixels off the design center to confirm arc text renders; screenshot. Repeat for `adventure`, `wrap`, `vstack`, `street`. Confirm front/back rotate + final proof still compose (they call `drawArt`). Stop preview.

- [ ] **Step 3: Full suite**

Run: `python -m pytest -q --no-header -p no:cacheprovider`
Expected: all pass (prior count + new tests). Quote the real number.

- [ ] **Step 4: Deploy loop (QuoteForge safe-deploy)**

```bash
git checkout -b feat/apparel-layout-studio   # if not already on a feature branch
# (all task commits live here)
git push -u origin feat/apparel-layout-studio
gh pr create --base main --title "feat(editor): apparel Layout Studio (12 preset layouts + arc text)" --body-file <body>
git checkout main && git merge --no-ff feat/apparel-layout-studio -m "Merge: apparel Layout Studio" && git push origin main
python -m quoteforge.admin backup-all && python -m quoteforge.admin verify-backup   # expect RESULT: HEALTHY
```

- [ ] **Step 5: Provide the UAT link**

`https://ajacobusa.github.io/members-reader/` (gate password `Jesus`) — note it reflects after the merge to `main`.

---

## Self-review notes

- **Spec coverage:** customer flow (Task 7), 12 layouts (Tasks 3+6), arc engine (Task 2), slots (Tasks 3+7), decor incl. waves (Task 5), fonts (Task 1), print-safety (bounds used throughout, Task 4), persistence + payload (Task 8), no-leak + tests + deploy (Task 9). Collage = single image (Task 6 `collage` uses one logo + frame decor) — matches v1 non-goal.
- **Branch note:** create the `feat/apparel-layout-studio` branch BEFORE Task 1 so every commit lands on it (the spec commit already exists on `main`). Adjust Task 9 Step 4 accordingly.
- **Freeform default preserved:** `drawArt` only diverts when `CURLAYOUT!=='freeform'`; `#mtextwrap` shows for freeform.
- **Naming consistency:** `CURLAYOUT`, `SLOTS`, `_slot`, `_layout`, `LAYOUTS`, `drawArcText`, `_drawLayout`, `_decor`, `_slotWording`, `renderLayoutGallery`, `renderSlotInputs`, `pickLayout`, `onSlot`, `SLOT_LABELS` used consistently across tasks.
