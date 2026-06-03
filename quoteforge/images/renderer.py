import time
import requests
from quoteforge.config import BANNERBEAR_API_KEY

BB_BASE = "https://api.bannerbear.com/v2"
HEADERS = {"Authorization": f"Bearer {BANNERBEAR_API_KEY}"}
POLL_INTERVAL = 2
MAX_POLLS = 30


def render_poster(template_uid: str, quote: str, background_url: str) -> str | None:
    """Submit a Bannerbear render job and return the finished image URL."""
    payload = {
        "template": template_uid,
        "modifications": [
            {"name": "quote_text", "text": quote},
            {"name": "background_image", "image_url": background_url},
        ],
    }
    resp = requests.post(f"{BB_BASE}/images", json=payload, headers=HEADERS)
    resp.raise_for_status()
    uid = resp.json()["uid"]

    for _ in range(MAX_POLLS):
        time.sleep(POLL_INTERVAL)
        poll = requests.get(f"{BB_BASE}/images/{uid}", headers=HEADERS)
        poll.raise_for_status()
        data = poll.json()
        if data["status"] == "done":
            return data["image_url"]
    return None
