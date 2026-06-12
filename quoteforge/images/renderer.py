"""Bannerbear poster renderer - submits a render job and polls until done."""
import time
import requests
from quoteforge.config import BANNERBEAR_API_KEY

BB_BASE = "https://api.bannerbear.com/v2"
POLL_INTERVAL = 2
MAX_POLLS = 30


def render_poster(template_uid: str, quote: str, background_url: str) -> str | None:
    """Submit a Bannerbear render job and return the finished image URL."""
    if not BANNERBEAR_API_KEY:
        raise ValueError("BANNERBEAR_API_KEY is not set. Open quoteforge/config.py and add your key.")
    headers = {"Authorization": f"Bearer {BANNERBEAR_API_KEY}"}
    payload = {
        "template": template_uid,
        "modifications": [
            {"name": "quote_text", "text": quote},
            {"name": "background_image", "image_url": background_url},
        ],
    }
    resp = requests.post(f"{BB_BASE}/images", json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    uid = resp.json()["uid"]

    for _ in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        poll = requests.get(f"{BB_BASE}/images/{uid}", headers=headers, timeout=15)
        poll.raise_for_status()
        data = poll.json()
        if data["status"] == "done":
            return data["image_url"]
    return None
