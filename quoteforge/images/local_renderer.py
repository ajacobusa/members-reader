"""Free, local poster renderer — composites a quote over a scenic background
using Pillow. Eliminates the Bannerbear subscription ($49/mo) for the common
"scenic background + centered quote" poster format.

Output is a print-ready PNG at the requested pixel size (300 DPI).
"""
import textwrap
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# Candidate fonts by mood/style — tries each path until one loads.
# Falls back to Pillow's default if none are present (still renders, just plainer).
_SERIF_FONTS = [
    "C:/Windows/Fonts/georgia.ttf",
    "C:/Windows/Fonts/times.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/Library/Fonts/Georgia.ttf",
]
_SANS_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _load_font(size: int, serif: bool = True) -> ImageFont.FreeTypeFont:
    candidates = _SERIF_FONTS if serif else _SANS_FONTS
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default(size=size)


def _download_background(url: str, size: tuple[int, int]) -> Image.Image:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    from io import BytesIO
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    return _cover_resize(img, size)


def _cover_resize(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize+crop so the image fully covers the target box (like CSS cover)."""
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    new = img.resize((int(iw * scale) + 1, int(ih * scale) + 1), Image.LANCZOS)
    nw, nh = new.size
    left, top = (nw - tw) // 2, (nh - th) // 2
    return new.crop((left, top, left + tw, top + th))


def _wrap_to_width(draw: ImageDraw.ImageDraw, text: str,
                   font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Greedy word wrap so each line fits within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        w = draw.textlength(trial, font=font)
        if w <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_local_poster(
    quote: str,
    output_path: Path,
    background_url: Optional[str] = None,
    background_path: Optional[Path] = None,
    size: tuple[int, int] = (5400, 7200),
    serif: bool = True,
    attribution: str = "",
) -> Path:
    """Render a poster PNG: quote centered over a darkened scenic background.

    Provide either background_url (downloaded) or background_path (local file).
    If neither is given, a deep solid color is used.
    size defaults to 18x24 in @ 300 DPI.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size

    # 1. Background
    if background_url:
        bg = _download_background(background_url, size)
    elif background_path and Path(background_path).exists():
        bg = _cover_resize(Image.open(background_path).convert("RGB"), size)
    else:
        bg = Image.new("RGB", size, (34, 51, 68))

    # 2. Darken for text contrast (semi-transparent overlay)
    bg = ImageEnhance.Brightness(bg).enhance(0.62)

    draw = ImageDraw.Draw(bg)

    # 3. Fit the quote: shrink font until it fits in ~70% width / ~60% height
    max_text_w = int(w * 0.78)
    max_text_h = int(h * 0.6)
    font_size = int(h * 0.075)
    while font_size > 24:
        font = _load_font(font_size, serif=serif)
        lines = _wrap_to_width(draw, quote, font, max_text_w)
        line_h = int(font_size * 1.3)
        total_h = line_h * len(lines)
        if total_h <= max_text_h:
            break
        font_size -= 8
    else:
        font = _load_font(font_size, serif=serif)
        lines = _wrap_to_width(draw, quote, font, max_text_w)
        line_h = int(font_size * 1.3)
        total_h = line_h * len(lines)

    # 4. Draw centered, with a soft shadow for readability
    y = (h - total_h) // 2
    shadow = (0, 0, 0)
    fill = (255, 255, 255)
    for line in lines:
        line_w = draw.textlength(line, font=font)
        x = (w - line_w) // 2
        draw.text((x + 4, y + 4), line, font=font, fill=shadow)
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h

    # 5. Optional attribution line
    if attribution:
        attr_font = _load_font(int(font_size * 0.5), serif=serif)
        aw = draw.textlength(attribution, font=attr_font)
        draw.text(((w - aw) // 2, y + int(font_size * 0.4)),
                  attribution, font=attr_font, fill=(230, 230, 230))

    # 6. Save at 300 DPI metadata
    bg.save(output_path, "PNG", dpi=(300, 300))
    return output_path
