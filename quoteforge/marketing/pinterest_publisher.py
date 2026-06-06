"""Pinterest auto-publisher — posts the generated pin pack via the Pinterest API.

Hands-free when configured: a scheduled job generates the pin pack and (if a
Pinterest API token + board are set AND PINTEREST_AUTOPILOT is on) posts each
pin automatically. Otherwise it's a safe DRY-RUN that still produces the images
+ pins.csv for manual bulk upload.

Uses only the standard library (urllib) — no new dependencies. Every network
call is best-effort; a failure on one pin never aborts the rest.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.pinterest.com/v5/pins"


def _post_pin(token: str, board_id: str, image_b64: str,
              title: str, description: str, link: str) -> tuple[bool, str]:
    body = json.dumps({
        "board_id": board_id,
        "title": title[:100],
        "description": description[:500],
        "link": link or None,
        "media_source": {"source_type": "image_base64",
                         "content_type": "image/png", "data": image_b64},
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return True, payload.get("id", "created")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read()[:160]!r}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def publish_pins(numbers=None, live: bool = False, kit_dir=None,
                 out_dir=None, limit: int | None = None) -> dict:
    """Generate the pin pack and (when live + configured) post each pin.

    live=False (default) → dry-run plan only, no API calls. The images +
    pins.csv are produced regardless so nothing blocks manual upload.
    """
    from quoteforge.config import (
        PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID, PINTEREST_AUTOPILOT)
    from quoteforge.marketing.pinterest import build_pin_pack

    pins = build_pin_pack(numbers=numbers, kit_dir=kit_dir, out_dir=out_dir)
    from quoteforge.config import OUTPUT_DIR
    pin_root = Path(out_dir) if out_dir else (OUTPUT_DIR / "pinterest")

    configured = bool(PINTEREST_ACCESS_TOKEN and PINTEREST_BOARD_ID)
    will_post = live and configured and PINTEREST_AUTOPILOT
    summary = {"generated": len(pins), "posted": 0, "failed": 0,
               "configured": configured, "live": will_post, "results": []}
    if not pins:
        summary["message"] = "No gallery art — run launch-kit first."
        return summary

    # Only product pins have real local images; themed pins are skipped for auto-post.
    postable = [p for p in pins if (pin_root / p.image).exists()]
    if limit:
        postable = postable[:limit]

    if not will_post:
        why = ("dry-run (pass live=True)" if not live else
               "Pinterest not configured" if not configured else
               "PINTEREST_AUTOPILOT is off")
        summary["message"] = (f"{len(postable)} pin(s) ready; not posted - {why}. "
                              f"Images + pins.csv are in {pin_root}.")
        return summary

    for p in postable:
        img = pin_root / p.image
        b64 = base64.b64encode(img.read_bytes()).decode("ascii")
        ok, detail = _post_pin(PINTEREST_ACCESS_TOKEN, PINTEREST_BOARD_ID,
                               b64, p.title, p.description, p.link)
        summary["posted" if ok else "failed"] += 1
        summary["results"].append({"title": p.title, "ok": ok, "detail": detail})
    summary["message"] = f"Posted {summary['posted']}/{len(postable)} pins to Pinterest."
    return summary
