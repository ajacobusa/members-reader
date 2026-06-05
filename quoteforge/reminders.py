"""Persistent setup reminders.

Lightweight to-do list for one-time setup items the OWNER must do (e.g. create a
customer-support Gmail). Reminders persist in a JSON file and are surfaced in the
daily report email every day until you mark them done — so nothing gets forgotten.

  admin remind add "text"   admin remind list   admin remind done N
"""
import json
from datetime import datetime
from pathlib import Path

# Seeded defaults — created on first use if the store doesn't exist yet.
_SEED = [
    "Create a dedicated customer-support Gmail for Joffiels, then set "
    "GMAIL_ADDRESS / GMAIL_APP_PASSWORD in .env to it.",
]


def _store() -> Path:
    from quoteforge.config import OUTPUT_DIR
    return OUTPUT_DIR / "reminders.json"


def _load() -> list[dict]:
    p = _store()
    if not p.exists():
        items = [{"id": i + 1, "text": t, "added": datetime.now().isoformat(timespec="seconds")}
                 for i, t in enumerate(_SEED)]
        _save(items)
        return items
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return []


def _save(items: list[dict]) -> None:
    p = _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, indent=2))


def get_reminders() -> list[dict]:
    return _load()


def add_reminder(text: str) -> int:
    items = _load()
    new_id = (max((i["id"] for i in items), default=0)) + 1
    items.append({"id": new_id, "text": text,
                  "added": datetime.now().isoformat(timespec="seconds")})
    _save(items)
    return new_id


def done_reminder(reminder_id: int) -> bool:
    items = _load()
    kept = [i for i in items if i["id"] != reminder_id]
    _save(kept)
    return len(kept) != len(items)


def format_reminders_text() -> str:
    items = _load()
    if not items:
        return "No pending setup reminders. [OK]"
    lines = ["Pending setup reminders:"]
    for i in items:
        lines.append(f"  #{i['id']}  {i['text']}")
    lines.append("\nMark done: python -m quoteforge.admin remind done <id>")
    return "\n".join(lines)


def reminders_html() -> str:
    items = _load()
    if not items:
        return ""
    rows = "".join(f"<li>{i['text']}</li>" for i in items)
    return (f"<h3>📌 Setup Reminders ({len(items)})</h3>"
            f"<ul>{rows}</ul>"
            f"<p style='font-size:12px;color:#777'>Clear with "
            f"<code>admin remind done &lt;id&gt;</code></p>")
