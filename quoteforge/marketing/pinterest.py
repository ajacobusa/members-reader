"""Pinterest pin-pack generator — the highest-ROI traffic source for POD.

For each launch listing it produces several Pinterest-optimized 2:3 (1000x1500)
pin images from the existing gallery art, plus a `pins.csv` schedule with
SEO'd titles, descriptions (with hashtags), board names and destination links —
ready to bulk-upload to Pinterest (manually or via the Pinterest API later).

It also emits standalone *gift-guide* and *seasonal* pin rows that point at the
shop home, so the board has evergreen + seasonal coverage, not just products.

Pure-Pillow; no new dependencies. Destination links default to the shop URL
(`ETSY_SHOP_URL`) until real per-listing URLs exist.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

PIN_W, PIN_H = 1000, 1500          # Pinterest's preferred 2:3 ratio
BRAND_GREEN = (15, 61, 46)
BRAND_GOLD = (201, 168, 76)

# (suffix, caption, board) for the per-product pin variations.
PIN_VARIANTS = [
    ("a_room", "The perfect personalized gift", "Personalized Wall Art"),
    ("b_detail", "Custom names, dates & your own words", "Gift Ideas"),
    ("c_gift", "A meaningful keepsake they'll treasure", "Sentimental Gifts"),
]


@dataclass
class Pin:
    listing_n: int
    image: str            # relative path of the generated pin PNG
    title: str
    description: str
    board: str
    link: str
    keywords: list[str] = field(default_factory=list)


def _hashtags(tags: list[str], k: int = 5) -> str:
    out = []
    for t in tags[:k]:
        out.append("#" + "".join(w.capitalize() for w in t.split()))
    return " ".join(out)


def _font(size: int):
    from PIL import ImageFont
    for name in ("Georgia.ttf", "georgia.ttf", "DejaVuSerif.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_pin_image(src: Path, out: Path, caption: str, shop: str) -> Path:
    """Compose a 1000x1500 pin: art on a brand panel + a caption bar + shop name."""
    from PIL import Image, ImageDraw
    canvas = Image.new("RGB", (PIN_W, PIN_H), BRAND_GREEN)
    art = Image.open(src).convert("RGB")
    # Fit the art into the top ~66% (a 1000x1000 square area, centered).
    box = 1000
    art.thumbnail((box - 60, box - 60), Image.LANCZOS)
    ax = (PIN_W - art.width) // 2
    ay = 40 + (box - 60 - art.height) // 2
    canvas.paste(art, (ax, ay))

    draw = ImageDraw.Draw(canvas)
    # Caption bar in the lower third.
    cap_font = _font(58)
    lines = _wrap(draw, caption, cap_font, PIN_W - 120)
    y = box + 70
    for ln in lines:
        w = draw.textlength(ln, font=cap_font)
        draw.text(((PIN_W - w) / 2, y), ln, font=cap_font, fill=BRAND_GOLD)
        y += 70
    # Shop name footer.
    shop_font = _font(40)
    sw = draw.textlength(shop, font=shop_font)
    draw.text(((PIN_W - sw) / 2, PIN_H - 90), shop, font=shop_font, fill=(232, 216, 168))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "PNG")
    return out


def build_pin_pack(numbers=None, kit_dir=None, out_dir=None) -> list[Pin]:
    """Generate the pin images + pins.csv. Returns the list of Pin rows."""
    from quoteforge.config import OUTPUT_DIR, SHOP_NAME
    try:
        from quoteforge.config import ETSY_SHOP_URL  # may not exist
    except Exception:  # noqa: BLE001
        ETSY_SHOP_URL = ""
    shop_link = ETSY_SHOP_URL or f"https://www.etsy.com/shop/{SHOP_NAME}"
    from quoteforge.etsy.listing_seo import build_launch_seo

    kit_dir = Path(kit_dir) if kit_dir else (OUTPUT_DIR / "launch_kit")
    out_dir = Path(out_dir) if out_dir else (OUTPUT_DIR / "pinterest")
    out_dir.mkdir(parents=True, exist_ok=True)

    bundles = build_launch_seo()
    if numbers:
        bundles = [b for b in bundles if b.listing_n in numbers]

    pins: list[Pin] = []
    for b in bundles:
        gallery = sorted(kit_dir.glob(f"{b.listing_n:02d}_*/gallery/*.png"))
        if not gallery:
            continue
        short = b.title.split(" | ")[0]
        for i, (suffix, caption, board) in enumerate(PIN_VARIANTS):
            src = gallery[i % len(gallery)]
            img_path = out_dir / f"{b.listing_n:02d}_{suffix}.png"
            make_pin_image(src, img_path, caption, SHOP_NAME)
            desc = (f"{caption}. {short} - personalized just for them. "
                    f"Free digital proof before printing. {_hashtags(b.tags)}")
            pins.append(Pin(
                listing_n=b.listing_n,
                image=str(img_path.relative_to(out_dir)),
                title=f"{short} - {caption}"[:100],
                description=desc[:500],
                board=board,
                link=shop_link,
                keywords=list(b.tags[:8]),
            ))

    if not pins:
        return []   # no gallery art yet — nothing to schedule

    # Evergreen + seasonal pins pointing at the shop home.
    pins.extend(_themed_pins(shop_link))

    # Write the schedule CSV.
    csv_path = out_dir / "pins.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["listing", "image", "title", "description", "board", "link", "keywords"])
        for p in pins:
            w.writerow([p.listing_n, p.image, p.title, p.description,
                        p.board, p.link, ", ".join(p.keywords)])
    return pins


def _themed_pins(shop_link: str) -> list[Pin]:
    themes = [
        ("Gift Guides", "10 Personalized Gifts They'll Actually Keep",
         "Gift Guides", ["personalized gift", "sentimental gift", "custom gift"]),
        ("Seasonal", "Last-Minute Personalized Gift Ideas",
         "Seasonal Gift Ideas", ["last minute gift", "custom wall art", "gift idea"]),
        ("Home Decor", "Meaningful Wall Art for Every Room",
         "Home Decor Inspiration", ["wall art", "home decor", "custom print"]),
    ]
    out = []
    for n, (tag, title, board, kws) in enumerate(themes, start=900):
        out.append(Pin(
            listing_n=n, image="(use a gift-guide collage)", title=title,
            description=f"{title}. {_hashtags(kws)}", board=board,
            link=shop_link, keywords=kws))
    return out
