"""See-it-before-you-buy frame/material previews.

Renders ONE real mockup per Format option (Poster, each Framed-frame, Canvas,
Acrylic, Metal) from a design, so the customer sees exactly what the chosen
frame looks like rather than assuming. These images double as Etsy variation
images (Etsy swaps the gallery photo when a buyer selects a Format).

`build_format_previews` -> {format_value: image_path}
`build_preview_page`     -> a self-contained HTML where clicking a Format swaps
                            the main image (the interactive "try the frame" demo).
"""
from __future__ import annotations

from pathlib import Path


def _format_values() -> list[tuple[str, str, str]]:
    """(format_value, renderer_frame_style, wall) for each sellable Format."""
    from quoteforge.images.room_mockup import FRAME_ID_TO_STYLE
    from quoteforge.etsy.frames import available_frames
    out = [("Poster (unframed)", "none", "warm-gray")]
    for f in available_frames():
        style = FRAME_ID_TO_STYLE.get(f.id, "black")
        out.append((f"Framed - {f.name}", style, "sage"))
    out += [("Canvas (gallery-wrapped)", "none", "greige"),
            ("Acrylic", "none", "blush"),
            ("Metal", "none", "warm-gray")]
    return out


def build_format_previews(poster_path, out_dir=None, size=(1000, 1000),
                          subset=None) -> dict:
    """Render one mockup per Format. Returns {format_value: Path}.
    `subset` (list of format_value) limits which are rendered."""
    from quoteforge.config import OUTPUT_DIR
    from quoteforge.images.room_mockup import render_room_mockup
    poster_path = Path(poster_path)
    out_dir = Path(out_dir) if out_dir else (OUTPUT_DIR / "frame_previews")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for value, style, wall in _format_values():
        if subset and value not in subset:
            continue
        slug = value.lower().replace(" ", "_").replace("(", "").replace(")", "")
        slug = slug.replace("-", "").replace("__", "_")
        out = out_dir / f"{slug}.png"
        render_room_mockup(poster_path, out, wall=wall, frame_style=style, size=size)
        result[value] = out
    return result


def format_preview_datauris(poster_path, max_dim=460, quality=68,
                            subset=None) -> list:
    """Render the Format mockups and return [(name, data_uri)] - small JPEGs for
    embedding an in-page frame picker without bloating the file. Renders to a
    temp dir (cleaned up). Returns [] if rendering fails."""
    import tempfile
    import shutil
    from quoteforge.etsy.listing_preview import _web_img
    tmp = Path(tempfile.mkdtemp(prefix="jf_fp_"))
    try:
        previews = build_format_previews(poster_path, out_dir=tmp,
                                         size=(620, 620), subset=subset)
        return [(name, _web_img(p, max_dim, quality))
                for name, p in previews.items()]
    except Exception:  # noqa: BLE001 — never break the page build
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_preview_page(poster_path, out_path=None, title="Preview your frame") -> Path:
    """Interactive page: click a Format to see that exact mockup before buying."""
    import json
    from quoteforge.config import OUTPUT_DIR, SHOP_NAME
    from quoteforge.etsy.listing_preview import _web_img

    previews = build_format_previews(poster_path)
    data = [{"name": k, "img": _web_img(v, 760)} for k, v in previews.items()]
    out_path = Path(out_path) if out_path else (OUTPUT_DIR / "frame_previews" / "try_a_frame.html")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SHOP_NAME} - {title}</title><style>
 body{{font-family:'Helvetica Neue',Arial,sans-serif;background:#f6f3ee;
   color:#23302b;margin:0}}
 .top{{background:#0f3d2e;color:#e8d8a8;padding:16px 22px;font-family:Georgia,serif}}
 .wrap{{max-width:900px;margin:20px auto;padding:0 16px}}
 #main{{width:100%;border-radius:12px;border:1px solid #e3ddd2;display:block}}
 .hint{{text-align:center;color:#5a6b62;font-size:14px;margin:10px 0}}
 .opts{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin:16px 0}}
 .opt{{border:1px solid #c9b98c;background:#fff;border-radius:20px;padding:8px 14px;
   cursor:pointer;font-size:13px}}
 .opt.sel{{background:#0f3d2e;color:#e8d8a8;border-color:#0f3d2e}}
</style></head><body>
<div class="top"><b>{SHOP_NAME}</b> &nbsp;|&nbsp; {title}</div>
<div class="wrap">
 <p class="hint">Tap a frame / material to see exactly how it looks - then you
   know before you buy.</p>
 <img id="main" src="">
 <div class="opts" id="opts"></div>
 <p class="hint">Frame not included unless you pick a Framed option. Canvas is
   gallery-wrapped ("open"). You choose the final product + size on Etsy.</p>
</div>
<script>
 const D = {json.dumps(data)};
 function pick(i){{
   document.getElementById('main').src = D[i].img;
   [...document.querySelectorAll('.opt')].forEach((e,j)=>
     e.classList.toggle('sel', i===j));
 }}
 document.getElementById('opts').innerHTML = D.map((d,i)=>
   `<div class="opt" onclick="pick(${{i}})">${{d.name}}</div>`).join('');
 pick(0);
</script></body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
