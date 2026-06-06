"""Multi-image listing pack generator.

Top Etsy shops win on imagery: a buyer decides in ~2 seconds from the gallery.
This turns ONE print design into a full set of Etsy gallery images — the single
highest-leverage conversion upgrade for Joffiels:

  1. hero_room      — the framed print styled on a wall (context = perceived value)
  2. closeup        — a detail crop showing print quality / premium paper
  3. size_chart     — all four sizes to scale so buyers pick confidently
  4. how_it_works   — the personalize -> proof -> approve -> ship flow
  5. whats_included — a trust-building checklist

Outputs are web-resolution listing images (2000x2000), NOT print files.
"""
from pathlib import Path

from PIL import Image, ImageDraw

from quoteforge.images.local_renderer import _load_font
from quoteforge.images.room_mockup import render_room_mockup, _frame_print

# Joffiels brand palette (matches logo/banner).
EMERALD = (15, 61, 46)
EMERALD_DARK = (10, 43, 33)
GOLD = (201, 168, 76)
CREAM = (239, 234, 224)
INK = (34, 40, 38)

SIZE = (2000, 2000)


def _canvas(bg=EMERALD) -> Image.Image:
    return Image.new("RGB", SIZE, bg)


def _center_text(draw, text, font, y, fill, w=SIZE[0]):
    tw = draw.textlength(text, font=font)
    draw.text(((w - tw) // 2, y), text, font=font, fill=fill)
    return y


def _check_image(img: Image.Image, name: str) -> dict:
    """Validate a generated image: correct size, RGB, non-blank."""
    ok = (img.size == SIZE and img.mode == "RGB")
    # crude non-blank check: more than one distinct colour
    extrema = img.convert("L").getextrema()
    non_blank = extrema[1] - extrema[0] > 10
    return {"name": name, "ok": ok and non_blank,
            "size": img.size, "mode": img.mode, "non_blank": non_blank}


# ── Image 1: hero room scene ─────────────────────────────────────

def _stamp_frame_badge(path: Path) -> Path:
    """Burn a small 'FRAME NOT INCLUDED' badge onto a framed mockup so shoppers
    who skim photos (not the description) aren't misled into expecting a frame."""
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    text = "FRAME NOT INCLUDED"
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arialbd.ttf", max(14, w // 36))
    except OSError:
        from PIL import ImageFont
        font = ImageFont.load_default()
    tw = draw.textlength(text, font=font)
    pad = max(8, w // 90)
    bh = (font.size if hasattr(font, "size") else 16) + pad * 2
    bw = tw + pad * 2
    x, y = w - bw - pad, h - bh - pad           # bottom-right corner
    draw.rectangle([x, y, x + bw, y + bh], fill=(15, 61, 46))
    draw.text((x + pad, y + pad), text, font=font, fill=(232, 216, 168))
    img.save(path, "PNG")
    return path


def hero_room(poster_path: Path, out: Path) -> Path:
    render_room_mockup(poster_path, out, wall="sage", frame_style="oak", size=SIZE)
    return _stamp_frame_badge(out)


# ── Image 2: close-up detail ─────────────────────────────────────

def closeup(poster_path: Path, out: Path) -> Path:
    poster = Image.open(poster_path).convert("RGB")
    pw, ph = poster.size
    # Crop the UPPER text band so the personalized name leads the detail shot
    # (the name is the selling point — never crop mid-sentence below it).
    cw, ch = int(pw * 0.78), int(ph * 0.30)
    left, top = (pw - cw) // 2, int(ph * 0.16)
    crop = poster.crop((left, top, left + cw, top + ch))
    crop = crop.resize((int(SIZE[0] * 0.82), int(SIZE[0] * 0.82 * ch / cw)),
                       Image.LANCZOS)

    canvas = _canvas(CREAM)
    draw = ImageDraw.Draw(canvas)
    cx = (SIZE[0] - crop.size[0]) // 2
    cy = int(SIZE[1] * 0.16)
    # gold accent border
    draw.rectangle([cx - 10, cy - 10, cx + crop.size[0] + 10, cy + crop.size[1] + 10],
                   outline=GOLD, width=8)
    canvas.paste(crop, (cx, cy))
    title = _load_font(86, serif=True)
    sub = _load_font(46, serif=False)
    _center_text(draw, "Premium 300 DPI Detail", title, cy + crop.size[1] + 70, EMERALD)
    _center_text(draw, "Crisp text - rich, fade-resistant inks - museum-grade paper",
                 sub, cy + crop.size[1] + 180, INK)
    canvas.save(out, "PNG")
    return out


# ── Image 3: size chart ──────────────────────────────────────────

_SIZES = [("8x10\"", 8, 10), ("11x14\"", 11, 14), ("16x20\"", 16, 20), ("18x24\"", 18, 24)]


def size_chart(poster_path: Path, out: Path) -> Path:
    poster = Image.open(poster_path).convert("RGB")
    canvas = _canvas(CREAM)
    draw = ImageDraw.Draw(canvas)
    title = _load_font(96, serif=True)
    _center_text(draw, "Choose Your Size", title, 90, EMERALD)

    # Scale the largest (18x24) to a reference pixel height; others relative.
    ref_h = SIZE[1] * 0.52
    max_in_h = 24
    gap = 60
    boxes = []
    for label, win, hin in _SIZES:
        h = int(ref_h * hin / max_in_h)
        w = int(h * win / hin)
        boxes.append((label, w, h))
    total_w = sum(b[1] for b in boxes) + gap * (len(boxes) - 1)
    x = (SIZE[0] - total_w) // 2
    baseline = int(SIZE[1] * 0.78)
    lab = _load_font(48, serif=False)
    for label, w, h in boxes:
        thumb = poster.resize((w, h), Image.LANCZOS)
        y = baseline - h
        draw.rectangle([x - 6, y - 6, x + w + 6, y + h + 6], outline=GOLD, width=5)
        canvas.paste(thumb, (x, y))
        tw = draw.textlength(label, font=lab)
        draw.text((x + (w - tw) // 2, baseline + 24), label, font=lab, fill=EMERALD)
        x += w + gap
    canvas.save(out, "PNG")
    return out


# ── Image 4: how it works ────────────────────────────────────────

_STEPS = [
    ("1", "Personalize", "Add the name, occasion & story at checkout"),
    ("2", "We Design", "We craft your custom piece and send a digital proof"),
    ("3", "You Approve", "Review the proof - reply APPROVED (or ask for changes)"),
    ("4", "We Ship", "Printed on premium stock and shipped with tracking"),
]


def how_it_works(out: Path) -> Path:
    canvas = _canvas(EMERALD)
    draw = ImageDraw.Draw(canvas)
    title = _load_font(110, serif=True)
    _center_text(draw, "How It Works", title, 120, GOLD)
    num_f = _load_font(80, serif=True)
    head_f = _load_font(64, serif=True)
    body_f = _load_font(44, serif=False)
    y = 380
    for num, head, body in _STEPS:
        # gold circle with number
        r = 70
        cx = 230
        draw.ellipse([cx - r, y - r, cx + r, y + r], fill=GOLD)
        nw = draw.textlength(num, font=num_f)
        draw.text((cx - nw / 2, y - 52), num, font=num_f, fill=EMERALD_DARK)
        draw.text((cx + 130, y - 60), head, font=head_f, fill=CREAM)
        draw.text((cx + 130, y + 14), body, font=body_f, fill=(210, 220, 212))
        y += 360
    canvas.save(out, "PNG")
    return out


# ── Image 5: what's included ─────────────────────────────────────

_INCLUDED = [
    "Personalized just for your recipient",
    "Free digital proof before we print",
    "Premium paper, framed & canvas options",
    "Made to order with care",
    "Ships directly to you with tracking",
    "Free replacement for any print defect",
]


def whats_included(out: Path) -> Path:
    canvas = _canvas(CREAM)
    draw = ImageDraw.Draw(canvas)
    title = _load_font(104, serif=True)
    _center_text(draw, "What's Included", title, 130, EMERALD)
    item_f = _load_font(56, serif=False)
    y = 420
    x = 250
    for text in _INCLUDED:
        # gold check disc
        r = 34
        draw.ellipse([x - r, y - r, x + r, y + r], fill=GOLD)
        draw.line([(x - 16, y), (x - 4, y + 14), (x + 18, y - 16)],
                  fill=CREAM, width=8, joint="curve")
        draw.text((x + 70, y - 36), text, font=item_f, fill=INK)
        y += 230
    canvas.save(out, "PNG")
    return out


# ── Orchestrator ─────────────────────────────────────────────────

def build_listing_pack(poster_path, output_dir=None) -> dict:
    """Generate the full Etsy gallery image set from a print design.
    Validates every image and returns a report."""
    from quoteforge.config import OUTPUT_DIR
    poster_path = Path(poster_path)
    out_dir = Path(output_dir) if output_dir else (OUTPUT_DIR / "listing_pack")
    out_dir.mkdir(parents=True, exist_ok=True)

    steps = [
        ("1_hero_room.png", lambda p: hero_room(poster_path, p)),
        ("2_closeup.png", lambda p: closeup(poster_path, p)),
        ("3_size_chart.png", lambda p: size_chart(poster_path, p)),
        ("4_how_it_works.png", lambda p: how_it_works(p)),
        ("5_whats_included.png", lambda p: whats_included(p)),
    ]
    results = []
    for fname, fn in steps:
        path = out_dir / fname
        fn(path)
        with Image.open(path) as im:
            chk = _check_image(im.convert("RGB"), fname)
        chk["file"] = str(path)
        results.append(chk)
    passed = sum(1 for r in results if r["ok"])
    return {"output_dir": str(out_dir), "total": len(results),
            "passed": passed, "failed": len(results) - passed,
            "images": results}


def format_pack_text(report: dict) -> str:
    lines = ["=" * 56, "LISTING IMAGE PACK", "=" * 56,
             f"Folder: {report['output_dir']}",
             f"Generated {report['passed']}/{report['total']} images:", ""]
    for r in report["images"]:
        lines.append(f"  [{'OK' if r['ok'] else 'XX'}] {r['name']} "
                     f"({r['size'][0]}x{r['size'][1]})")
    lines.append("\nUpload these to the Etsy listing gallery (hero first).")
    lines.append("=" * 56)
    return "\n".join(lines)
