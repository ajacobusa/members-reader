"""Per-customer record folders (one folder per customer ID).

Every customer gets a stable ID derived from their email and a private folder
under OUTPUT_DIR/customers/<id>/ holding details.json (profile + order history),
their uploaded photos, and proofs. Keeps each customer's info organized and
self-contained for service, reorders, and audits.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


def customer_id(email: str, name: str = "") -> str:
    """Stable short ID from email (or name fallback). e.g. C1a2b3c4d5."""
    key = (email or name or "guest").strip().lower()
    return "C" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def customer_dir(email: str, name: str = "") -> Path:
    """Path of the customer's record folder under OUTPUT_DIR/customers/."""
    from quoteforge.config import OUTPUT_DIR
    return OUTPUT_DIR / "customers" / customer_id(email, name)


def ensure_customer(email: str, name: str = "") -> Path:
    """Create (or load) the customer's folder + details.json. Returns the path."""
    d = customer_dir(email, name)
    (d / "uploads").mkdir(parents=True, exist_ok=True)
    (d / "proofs").mkdir(parents=True, exist_ok=True)
    details = d / "details.json"
    if not details.exists():
        details.write_text(json.dumps({
            "customer_id": customer_id(email, name),
            "email": email, "name": name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "orders": [],
        }, indent=2), encoding="utf-8")
    return d


def record_order(email: str, order: dict, name: str = "") -> dict:
    """Append an order summary to the customer's details.json. Returns the record."""
    ensure_customer(email, name or order.get("customer_name", ""))
    details = customer_dir(email, name) / "details.json"
    try:
        data = json.loads(details.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {"orders": []}
    data.setdefault("orders", []).append({
        "order_id": order.get("order_id") or order.get("etsy_order_id"),
        "occasion": order.get("occasion"),
        "recipient": order.get("recipient_name"),
        "vendor": order.get("vendor", "gelato"),
        "channel": order.get("channel", "etsy"),
        "sale_price": order.get("sale_price"),
        "at": datetime.now().isoformat(timespec="seconds"),
    })
    if order.get("customer_name") and not data.get("name"):
        data["name"] = order["customer_name"]
    details.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def save_upload(email: str, src_path, name: str = "") -> Path | None:
    """Copy a customer-supplied photo into their uploads/ folder."""
    src = Path(src_path)
    if not src.exists():
        return None
    dest_dir = ensure_customer(email, name) / "uploads"
    dest = dest_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{src.name}"
    shutil.copy2(src, dest)
    return dest
