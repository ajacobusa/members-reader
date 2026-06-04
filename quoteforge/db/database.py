"""SQLite database — local mirror of Airtable. Products / Orders / Templates tables."""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from quoteforge.config import OUTPUT_DIR

DB_PATH: Path = OUTPUT_DIR / "quoteforge.db"


@contextmanager
def _conn():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist."""
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            product_id      TEXT PRIMARY KEY,
            etsy_listing_id TEXT,
            template_id     TEXT,
            category        TEXT NOT NULL,
            gelato_sku      TEXT NOT NULL,
            title           TEXT NOT NULL,
            price_usd       REAL NOT NULL,
            gelato_cost_usd REAL NOT NULL,
            product_type    TEXT NOT NULL,
            size            TEXT NOT NULL,
            active          INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id        TEXT PRIMARY KEY,
            etsy_order_id   TEXT UNIQUE,
            customer_name   TEXT,
            customer_email  TEXT,
            recipient_name  TEXT NOT NULL,
            sender_name     TEXT,
            relationship    TEXT,
            occasion        TEXT NOT NULL,
            scenery         TEXT,
            tone            TEXT,
            memory          TEXT,
            output_style    TEXT DEFAULT 'Personal Letter',
            generated_quote TEXT,
            artwork_url     TEXT,
            drive_file_id   TEXT,
            gelato_order_id TEXT,
            tracking_number TEXT,
            status          TEXT DEFAULT 'received',
            proof_sent      INTEGER DEFAULT 0,
            proof_approved  INTEGER DEFAULT 0,
            upsell_sent     INTEGER DEFAULT 0,
            review_sent     INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS templates (
            template_id     TEXT PRIMARY KEY,
            theme           TEXT NOT NULL,
            canva_id        TEXT,
            bannerbear_uid  TEXT,
            scenery_type    TEXT,
            category        TEXT,
            width_px        INTEGER,
            height_px       INTEGER,
            product_type    TEXT DEFAULT 'poster',
            active          INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pipeline_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT NOT NULL,
            stage           TEXT NOT NULL,
            status          TEXT NOT NULL,
            message         TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        """)


# ── Order CRUD ───────────────────────────────────────────────────

def create_order(data: dict) -> str:
    """Insert a new order. Returns order_id."""
    order_id = data.get("order_id") or f"QF-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:18]}"
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO orders
            (order_id, etsy_order_id, customer_name, customer_email,
             recipient_name, sender_name, relationship, occasion,
             scenery, tone, memory, output_style, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            order_id,
            data.get("etsy_order_id"),
            data.get("customer_name", ""),
            data.get("customer_email", ""),
            data.get("recipient_name", ""),
            data.get("sender_name", ""),
            data.get("relationship", ""),
            data.get("occasion", ""),
            data.get("scenery", "Mountains"),
            data.get("tone", "Inspirational & Motivational"),
            data.get("memory", ""),
            data.get("output_style", "Personal Letter"),
            "received",
        ))
    return order_id


def update_order(order_id: str, **fields) -> None:
    """Update specific fields on an order."""
    fields["updated_at"] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [order_id]
    with _conn() as conn:
        conn.execute(f"UPDATE orders SET {set_clause} WHERE order_id=?", values)


def get_order(order_id: str) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        return dict(row) if row else None


def get_orders_by_status(status: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_orders(limit: int = 100) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def log_pipeline_stage(order_id: str, stage: str, status: str, message: str = "") -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO pipeline_log (order_id, stage, status, message) VALUES (?,?,?,?)",
            (order_id, stage, status, message),
        )


def get_pipeline_log(order_id: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pipeline_log WHERE order_id=? ORDER BY created_at",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Product CRUD ─────────────────────────────────────────────────

def upsert_product(data: dict) -> None:
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO products
            (product_id, etsy_listing_id, template_id, category, gelato_sku,
             title, price_usd, gelato_cost_usd, product_type, size)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            data["product_id"], data.get("etsy_listing_id"), data.get("template_id"),
            data["category"], data["gelato_sku"], data["title"],
            data["price_usd"], data["gelato_cost_usd"],
            data["product_type"], data["size"],
        ))


def get_products_by_category(category: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM products WHERE category=? AND active=1", (category,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Template CRUD ─────────────────────────────────────────────────

def upsert_template(data: dict) -> None:
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO templates
            (template_id, theme, canva_id, bannerbear_uid, scenery_type,
             category, width_px, height_px, product_type)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            data["template_id"], data["theme"], data.get("canva_id"),
            data.get("bannerbear_uid"), data.get("scenery_type"),
            data.get("category"), data.get("width_px", 5400),
            data.get("height_px", 7200), data.get("product_type", "poster"),
        ))


def get_templates_by_scenery(scenery_type: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM templates WHERE scenery_type=? AND active=1", (scenery_type,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_order_stats() -> dict:
    """Return aggregate order statistics for the dashboard."""
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        by_status = {}
        for row in conn.execute("SELECT status, COUNT(*) as n FROM orders GROUP BY status"):
            by_status[row["status"]] = row["n"]
        return {"total": total, "by_status": by_status}
