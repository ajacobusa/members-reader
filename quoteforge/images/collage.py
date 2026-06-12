"""Build a hero collage from source images (dog / scenery / lifestyle / family).

Drop images into brand/collage_src/ (any JPG/PNG) and this tiles them into a
single wide hero image saved to brand/hero.jpg - which the shop-home page then
uses as its hero automatically. A graceful placeholder tile is drawn for any
empty slot (e.g. a 'Your family photo here' tile) so the collage always looks
complete.
"""
from __future__ import annotations

from pathlib import Path

BRAND_GREEN = (16, 61, 46)
GOLD = (201, 168, 76)
CREAM = (247, 244, 238)


def _placeholder(draw, box, label):
    """Draw a brand-green placeholder tile with a centered gold label."""
    from PIL import ImageFont
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=BRAND_GREEN)
    try:
        font = ImageFont.truetype("Georgia.ttf", max(14, (x1 - x0) // 14))
    except OSError:
        font = ImageFont.load_default()
    tw = draw.textlength(label, font=font)
    draw.text(((x0 + x1) / 2 - tw / 2, (y0 + y1) / 2 - 10), label,
              font=font, fill=GOLD)


def build_collage(src_dir=None, out_path=None, size=(1600, 600),
                  slots=4, labels=None) -> Path:
    """Tile up to `slots` images side by side into one hero banner."""
    from PIL import Image, ImageDraw
    brand = Path("brand")
    src_dir = Path(src_dir) if src_dir else (brand / "collage_src")
    out_path = Path(out_path) if out_path else (brand / "hero.jpg")
    labels = labels or ["Cute companions", "Your family photo here",
                        "Beautiful scenery", "Made with love"]

    imgs = []
    if src_dir.exists():
        imgs = sorted([p for p in src_dir.iterdir()
                       if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    W, H = size
    tile_w = W // slots
    canvas = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(canvas)
    for i in range(slots):
        box = (i * tile_w, 0, (i + 1) * tile_w if i < slots - 1 else W, H)
        if i < len(imgs):
            try:
                im = Image.open(imgs[i]).convert("RGB")
                # cover-crop to the tile
                tw, th = box[2] - box[0], H
                scale = max(tw / im.width, th / im.height)
                im = im.resize((int(im.width * scale), int(im.height * scale)),
                               Image.LANCZOS)
                left = (im.width - tw) // 2
                top = (im.height - th) // 2
                im = im.crop((left, top, left + tw, top + th))
                canvas.paste(im, (box[0], 0))
            except Exception:  # noqa: BLE001
                _placeholder(draw, box, labels[i % len(labels)])
        else:
            _placeholder(draw, box, labels[i % len(labels)])
        if i > 0:   # thin gold divider
            draw.rectangle((box[0] - 2, 0, box[0] + 2, H), fill=GOLD)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=88)
    return out_path
