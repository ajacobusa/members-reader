"""Listing video generator — a slow, premium Ken-Burns MP4 from a mockup.

Etsy ranks listings WITH video higher, and most small shops don't have one. This
turns the hero room mockup into a short (5-8s), silent, square MP4 with a gentle
zoom - a polished, professional touch with zero extra design work. Uses imageio +
ffmpeg (already available); no external service.

Etsy video specs honoured: 5-15s, >=720p, square, MP4, no audio.
"""
from pathlib import Path


def make_listing_video(image_path, out_path, seconds: float = 6.0,
                       fps: int = 24, zoom: float = 1.12,
                       size: int = 1080) -> Path:
    """Render a slow zoom-in MP4 from a still image."""
    from PIL import Image
    import imageio.v2 as imageio

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src = Image.open(image_path).convert("RGB")
    sw, sh = src.size
    n_frames = max(2, int(seconds * fps))

    writer = imageio.get_writer(
        str(out_path), fps=fps, codec="libx264", quality=8,
        macro_block_size=None, ffmpeg_log_level="error")
    try:
        for i in range(n_frames):
            t = i / (n_frames - 1)
            scale = 1.0 + (zoom - 1.0) * t          # 1.0 -> zoom
            cw, ch = sw / scale, sh / scale
            left, top = (sw - cw) / 2, (sh - ch) / 2
            frame = src.crop((int(left), int(top),
                              int(left + cw), int(top + ch)))
            frame = frame.resize((size, size), Image.LANCZOS)
            writer.append_data(_to_array(frame))
    finally:
        writer.close()
    return out_path


def _to_array(img):
    """Convert a PIL image to a numpy array for the video writer."""
    import numpy as np
    return np.asarray(img)


def build_video_for_listing(folder) -> Path | None:
    """Make a listing video from a kit folder's hero room mockup, if present."""
    folder = Path(folder)
    hero = next(iter(folder.glob("gallery/1_hero_room.png")), None) \
        or next(iter(folder.glob("**/1_hero_room.png")), None)
    if not hero:
        return None
    return make_listing_video(hero, folder / "listing_video.mp4")
