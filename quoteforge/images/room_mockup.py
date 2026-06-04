"""Free styled-room mockup renderer.

The single biggest conversion lever for high-ticket wall art is CONTEXT: a
framed print shown on a styled wall sells for several times what the same print
sells for on a plain white background. This module takes a finished poster PNG
and composites it into a tasteful framed-on-wall lifestyle scene using Pillow —
no paid mockup service, no real-photo licensing required.

Two modes:
  - Synthetic scene (default): a soft gradient wall + baseboard + framed,
    matted print with a realistic drop shadow.
  - Real room photo: pass room_background_path and the framed print is composited
    onto it (centered in the upper portion, where wall art naturally hangs).

Output is a web-resolution listing image (not for printing) — these are the
images you upload to the Etsy gallery, NOT the print file.
"""
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

# Wall color presets (top, bottom) for a subtle vertical gradient.
WALL_PRESETS = {
    "warm-gray": ((233, 229, 222), (214, 208, 198)),
    "sage":      ((222, 228, 214), (200, 209, 190)),
    "blush":     ((238, 226, 224), (223, 206, 203)),
    "greige":    ((226, 222, 215), (205, 199, 189)),
}

# Frame styles: (frame_color, mat_color, frame_fraction_of_print_width).
FRAME_STYLES = {
    "black": ((28, 28, 30), (250, 250, 248), 0.045),
    "white": ((248, 248, 246), (252, 252, 250), 0.045),
    "oak":   ((178, 142, 96), (250, 248, 244), 0.05),
    "walnut": ((92, 64, 48), (250, 248, 244), 0.05),
}


def _gradient_wall(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    """A soft top-to-bottom vertical gradient wall."""
    w, h = size
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        base.putpixel((0, y), tuple(
            int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return base.resize(size)


def _add_baseboard(wall: Image.Image, wall_color_bottom: tuple) -> None:
    """Draw a floor strip + baseboard at the bottom for grounding."""
    w, h = wall.size
    draw = ImageDraw.Draw(wall)
    floor_top = int(h * 0.82)
    # Floor: slightly darker, warmer band
    floor = tuple(max(0, c - 26) for c in wall_color_bottom)
    draw.rectangle([0, floor_top, w, h], fill=floor)
    # Baseboard: thin lighter trim line
    bb = tuple(min(255, c + 14) for c in wall_color_bottom)
    draw.rectangle([0, floor_top, w, floor_top + int(h * 0.012)], fill=bb)


def _frame_print(poster: Image.Image, frame_style: str,
                 target_w: int) -> Image.Image:
    """Wrap the poster in a mat + frame, preserving its aspect ratio."""
    frame_color, mat_color, frame_frac = FRAME_STYLES.get(
        frame_style, FRAME_STYLES["black"])
    # Resize poster to target inner width
    pw, ph = poster.size
    inner_w = target_w
    inner_h = int(ph * (inner_w / pw))
    art = poster.resize((inner_w, inner_h), Image.LANCZOS)

    mat = max(8, int(inner_w * 0.06))
    frame = max(10, int(inner_w * frame_frac))
    total_w = inner_w + 2 * (mat + frame)
    total_h = inner_h + 2 * (mat + frame)

    framed = Image.new("RGB", (total_w, total_h), frame_color)
    # Mat
    mdraw = ImageDraw.Draw(framed)
    mdraw.rectangle([frame, frame, total_w - frame, total_h - frame],
                    fill=mat_color)
    # Inner art
    framed.paste(art, (frame + mat, frame + mat))
    # Subtle inner bevel line around the art
    mdraw.rectangle(
        [frame + mat - 2, frame + mat - 2,
         total_w - frame - mat + 1, total_h - frame - mat + 1],
        outline=tuple(max(0, c - 40) for c in mat_color), width=2)
    return framed


def _paste_with_shadow(scene: Image.Image, framed: Image.Image,
                       top_left: tuple[int, int]) -> None:
    """Paste framed art onto the scene with a soft drop shadow behind it."""
    x, y = top_left
    fw, fh = framed.size
    offset = max(6, int(fw * 0.02))
    blur = max(8, int(fw * 0.03))
    # Shadow layer
    shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rectangle([x + offset, y + offset, x + fw + offset, y + fh + offset],
                    fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    scene.paste(Image.new("RGB", scene.size, (0, 0, 0)), (0, 0), shadow)
    scene.paste(framed, (x, y))


def render_room_mockup(
    poster_path: Path,
    output_path: Path,
    wall: str = "warm-gray",
    frame_style: str = "black",
    room_background_path: Optional[Path] = None,
    size: tuple[int, int] = (1600, 1600),
) -> Path:
    """Composite a finished poster into a styled-room lifestyle mockup.

    poster_path : the rendered print PNG (from render_local_poster).
    wall        : a WALL_PRESETS key (ignored if room_background_path given).
    frame_style : a FRAME_STYLES key.
    Returns the mockup path (web-resolution listing image).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    poster = Image.open(poster_path).convert("RGB")

    # 1. Scene background
    if room_background_path and Path(room_background_path).exists():
        scene = Image.open(room_background_path).convert("RGB").resize(size)
    else:
        top, bottom = WALL_PRESETS.get(wall, WALL_PRESETS["warm-gray"])
        scene = _gradient_wall(size, top, bottom)
        _add_baseboard(scene, bottom)

    w, h = size
    # 2. Frame the print at ~46% of scene width
    framed = _frame_print(poster, frame_style, target_w=int(w * 0.46))
    fw, fh = framed.size
    # Cap height so it never collides with the floor band
    max_fh = int(h * 0.66)
    if fh > max_fh:
        scale = max_fh / fh
        framed = framed.resize((int(fw * scale), int(fh * scale)), Image.LANCZOS)
        fw, fh = framed.size

    # 3. Hang it: horizontally centered, vertically in the upper-middle
    x = (w - fw) // 2
    y = int(h * 0.12)
    _paste_with_shadow(scene, framed, (x, y))

    scene.save(output_path, "PNG")
    return output_path
