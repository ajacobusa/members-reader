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
    # timeout=30 → wait up to 30s for a lock instead of failing instantly.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL allows concurrent readers + one writer (vs default which blocks both).
    # busy_timeout makes writers retry instead of raising "database is locked".
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
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
            mockup_url      TEXT,
            drive_file_id   TEXT,
            gelato_product_uid TEXT,
            gelato_order_id TEXT,
            tracking_number TEXT,
            status          TEXT DEFAULT 'received',
            proof_sent      INTEGER DEFAULT 0,
            proof_approved  INTEGER DEFAULT 0,
            proof_approved_at TEXT,
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

        CREATE TABLE IF NOT EXISTS customer_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT NOT NULL,
            message_type    TEXT NOT NULL,
            message_body    TEXT NOT NULL,
            sent            INTEGER DEFAULT 0,
            scheduled_for   TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS upsells (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT NOT NULL,
            offer_type      TEXT NOT NULL,
            offer_body      TEXT NOT NULL,
            accepted        INTEGER DEFAULT 0,
            sent            INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        TEXT NOT NULL,
            review_message  TEXT NOT NULL,
            scheduled_for   TEXT,
            sent            INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS api_costs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            provider        TEXT NOT NULL,          -- 'anthropic', 'gelato', ...
            model           TEXT,
            operation       TEXT,                   -- what it was for
            input_tokens    INTEGER DEFAULT 0,
            output_tokens   INTEGER DEFAULT 0,
            units           INTEGER DEFAULT 0,      -- non-token calls (e.g. images)
            cost_usd        REAL DEFAULT 0,
            order_id        TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kind            TEXT NOT NULL,          -- e.g. 'issue', 'refund'
            ref             TEXT,                   -- order id or related ref
            summary         TEXT NOT NULL,          -- what the bot wants to do
            proposed_action TEXT,                   -- machine-readable action key
            payload         TEXT,                   -- JSON context for execution
            confidence      REAL DEFAULT 0,
            risk            TEXT DEFAULT 'low',
            status          TEXT DEFAULT 'pending', -- pending|approved|rejected|auto
            decided_by      TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            decided_at      TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL UNIQUE,
            source      TEXT DEFAULT 'manual',   -- insert|linktree|website|etsy|gift_recipient
            consent     TEXT DEFAULT 'pending',  -- pending|yes|no (marketing opt-in)
            created_at  TEXT DEFAULT (datetime('now'))
        );
        """)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply lightweight column migrations to pre-existing databases."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
    if "gelato_product_uid" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN gelato_product_uid TEXT")
    if "sale_price" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN sale_price REAL")
    if "gelato_cost" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN gelato_cost REAL")
    if "mockup_url" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN mockup_url TEXT")
    if "proof_approved_at" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN proof_approved_at TEXT")
    subcols = {row["name"] for row in conn.execute("PRAGMA table_info(subscribers)")}
    if subcols and "consent" not in subcols:
        conn.execute("ALTER TABLE subscribers ADD COLUMN consent TEXT DEFAULT 'pending'")


# ── Order CRUD ───────────────────────────────────────────────────

def create_order(data: dict) -> str:
    """Insert a new order. Returns order_id."""
    order_id = data.get("order_id") or f"QF-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:18]}"
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO orders
            (order_id, etsy_order_id, customer_name, customer_email,
             recipient_name, sender_name, relationship, occasion,
             scenery, tone, memory, output_style, status,
             sale_price, gelato_cost)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            data.get("sale_price"),   # None until a real sale price is known
            data.get("gelato_cost"),  # None until a real print cost is known
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


def get_order_by_etsy_id(etsy_order_id: str) -> Optional[dict]:
    """Look up an order by its Etsy order ID — used for idempotency.

    Lets the webhook detect a retried/duplicate delivery and skip reprocessing
    (prevents duplicate quotes and duplicate Gelato charges).
    """
    if not etsy_order_id:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE etsy_order_id=?", (etsy_order_id,)
        ).fetchone()
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


# ── Customer message persistence ─────────────────────────────────

def save_customer_message(order_id: str, message_type: str, message_body: str,
                          scheduled_for: str = "", sent: bool = False) -> int:
    """Persist a customer message (order_received, proof_ready, shipped, etc.)."""
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO customer_messages
               (order_id, message_type, message_body, scheduled_for, sent)
               VALUES (?,?,?,?,?)""",
            (order_id, message_type, message_body, scheduled_for, int(sent)),
        )
        return cur.lastrowid


def get_customer_messages(order_id: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM customer_messages WHERE order_id=? ORDER BY created_at",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_message_sent(message_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE customer_messages SET sent=1 WHERE id=?", (message_id,))


# ── Upsell persistence ───────────────────────────────────────────

def save_upsell(order_id: str, offer_type: str, offer_body: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO upsells (order_id, offer_type, offer_body) VALUES (?,?,?)",
            (order_id, offer_type, offer_body),
        )
        return cur.lastrowid


def get_upsells(order_id: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM upsells WHERE order_id=? ORDER BY created_at", (order_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Review persistence ───────────────────────────────────────────

def save_review(order_id: str, review_message: str, scheduled_for: str = "") -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO reviews (order_id, review_message, scheduled_for)
               VALUES (?,?,?)""",
            (order_id, review_message, scheduled_for),
        )
        return cur.lastrowid


def get_pending_reviews() -> list[dict]:
    """Return reviews scheduled but not yet sent."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE sent=0 ORDER BY scheduled_for"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_review_sent(review_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE reviews SET sent=1 WHERE id=?", (review_id,))


# ── Mailing-list subscribers (audience you own) ──────────────────

def add_subscriber(email: str, source: str = "manual",
                   consent: str = "pending") -> bool:
    """Add an email to the list. Returns True if newly added, False if duplicate
    or invalid. Idempotent. `consent` tracks marketing opt-in (pending|yes|no);
    only target consent='yes' (or your own buyers) in marketing sends."""
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return False
    with _conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO subscribers (email, source, consent) VALUES (?,?,?)",
            (email, source, consent))
        return cur.rowcount > 0


def get_subscribers() -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM subscribers ORDER BY created_at DESC")]


def subscriber_count() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM subscribers").fetchone()["n"]


# ── Human-approval queue (autopilot escalations) ─────────────────

def enqueue_approval(kind: str, summary: str, ref: str = "",
                     proposed_action: str = "", payload: str = "",
                     confidence: float = 0.0, risk: str = "low",
                     status: str = "pending", decided_by: str = "") -> int:
    """Record a decision needing (or recording) human sign-off. status='auto'
    logs a bot decision that was executed without a human."""
    from datetime import datetime
    decided_at = datetime.now().isoformat(timespec="seconds") \
        if status != "pending" else None
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO approvals
               (kind, ref, summary, proposed_action, payload, confidence,
                risk, status, decided_by, decided_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (kind, ref, summary, proposed_action, payload, confidence,
             risk, status, decided_by, decided_at))
        return cur.lastrowid


def get_pending_approvals() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def get_approval(approval_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM approvals WHERE id=?",
                           (approval_id,)).fetchone()
        return dict(row) if row else None


def resolve_approval(approval_id: int, status: str,
                     decided_by: str = "owner") -> None:
    from datetime import datetime
    with _conn() as conn:
        conn.execute(
            "UPDATE approvals SET status=?, decided_by=?, decided_at=? WHERE id=?",
            (status, decided_by, datetime.now().isoformat(timespec="seconds"),
             approval_id))


# ── API cost tracking ────────────────────────────────────────────

def record_api_cost(provider: str, cost_usd: float, model: str = "",
                    operation: str = "", input_tokens: int = 0,
                    output_tokens: int = 0, units: int = 0,
                    order_id: str = "") -> int:
    # Store created_at in LOCAL time so the daily cost report's local-date
    # window matches (SQLite's datetime('now') is UTC and would misbucket
    # evening-local costs into the next day).
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO api_costs
               (provider, model, operation, input_tokens, output_tokens,
                units, cost_usd, order_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (provider, model, operation, input_tokens, output_tokens,
             units, round(cost_usd, 6), order_id, created))
        return cur.lastrowid


def get_api_costs(since_iso: str = "", until_iso: str = "") -> list[dict]:
    """Return cost rows in [since, until). Both bounds optional."""
    q = "SELECT * FROM api_costs WHERE 1=1"
    params: list = []
    if since_iso:
        q += " AND created_at >= ?"; params.append(since_iso)
    if until_iso:
        q += " AND created_at < ?"; params.append(until_iso)
    q += " ORDER BY created_at"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


# ── Backup / recovery ────────────────────────────────────────────

def db_maintenance() -> dict:
    """Run database health + performance maintenance.

    - integrity_check : detects corruption early
    - wal_checkpoint  : flushes the write-ahead log back into the main file
    - VACUUM          : reclaims space and defragments for faster queries
    Returns metrics (size before/after, integrity result). Safe to run daily.
    """
    if not DB_PATH.exists():
        return {"ran": False, "reason": "no database yet"}
    size_before = DB_PATH.stat().st_size
    with _conn() as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # VACUUM cannot run inside a transaction/context-managed connection
    vac = sqlite3.connect(DB_PATH, timeout=30)
    try:
        vac.execute("VACUUM")
    finally:
        vac.close()
    size_after = DB_PATH.stat().st_size
    return {
        "ran": True,
        "integrity": integrity,                      # "ok" when healthy
        "size_before_kb": round(size_before / 1024, 1),
        "size_after_kb": round(size_after / 1024, 1),
        "reclaimed_kb": round((size_before - size_after) / 1024, 1),
    }


def backup_database(backup_dir: Optional[Path] = None) -> Optional[Path]:
    """Create a consistent, timestamped snapshot of the database.

    Uses SQLite's online backup API (safe even while the DB is in use, unlike
    a raw file copy). Returns the backup path, or None if the DB doesn't exist.
    """
    if not DB_PATH.exists():
        return None
    if backup_dir is None:
        backup_dir = DB_PATH.parent / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"quoteforge_{timestamp}.db"

    source = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(backup_path)
    try:
        source.backup(dest)  # atomic online backup
    finally:
        dest.close()
        source.close()
    return backup_path


def prune_old_backups(backup_dir: Optional[Path] = None,
                      retention_days: Optional[int] = None,
                      keep: Optional[int] = None) -> int:
    """Prune database backups, returning the count deleted.

    Age-based by default: any backup older than `retention_days` (config
    BACKUP_RETENTION_DAYS, default 3) is deleted, but the MOST RECENT backup is
    always kept regardless of age, so we never end up with zero backups.

    `keep` (legacy count-based) still works if explicitly passed.
    """
    from datetime import datetime, timedelta
    if backup_dir is None:
        backup_dir = DB_PATH.parent / "db_backups"
    if not backup_dir.exists():
        return 0
    backups = sorted(backup_dir.glob("quoteforge_*.db"), reverse=True)  # newest first
    if not backups:
        return 0

    deleted = 0
    if keep is not None:  # legacy count-based retention
        for old in backups[keep:]:
            old.unlink(); deleted += 1
        return deleted

    if retention_days is None:
        from quoteforge.config import BACKUP_RETENTION_DAYS
        retention_days = BACKUP_RETENTION_DAYS
    cutoff = datetime.now() - timedelta(days=retention_days)
    # Always keep the newest backup BY MODIFICATION TIME (never end up with zero),
    # then prune any other backup older than the cutoff.
    newest = max(backups, key=lambda p: p.stat().st_mtime)
    for old in backups:
        if old == newest:
            continue
        if datetime.fromtimestamp(old.stat().st_mtime) < cutoff:
            old.unlink(); deleted += 1
    return deleted


def list_backups(backup_dir: Optional[Path] = None) -> list[Path]:
    """Return available backups, newest first."""
    if backup_dir is None:
        backup_dir = DB_PATH.parent / "db_backups"
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("quoteforge_*.db"), reverse=True)


def restore_database(backup_path: Optional[Path] = None,
                     backup_dir: Optional[Path] = None) -> Optional[Path]:
    """Restore the live DB from a backup (newest if not specified).

    Safety: the current DB is itself backed up first (so a restore is reversible).
    Returns the path that was restored from, or None if no backup exists.
    """
    import shutil
    if backup_path is None:
        backups = list_backups(backup_dir)
        if not backups:
            return None
        backup_path = backups[0]
    if not backup_path.exists():
        return None
    # Back up current state before overwriting (reversible restore)
    if DB_PATH.exists():
        backup_database()
    shutil.copy2(backup_path, DB_PATH)
    return backup_path


def daily_order_report() -> dict:
    """Summary for the daily order-review process.

    Returns counts by status plus the orders needing human attention
    (pending proof, and errors).
    """
    with _conn() as conn:
        by_status: dict[str, int] = {}
        for row in conn.execute("SELECT status, COUNT(*) n FROM orders GROUP BY status"):
            by_status[row["status"]] = row["n"]
        needs_attention = [
            dict(r) for r in conn.execute(
                "SELECT order_id, recipient_name, occasion, status FROM orders "
                "WHERE status IN ('proof_sent','error') ORDER BY created_at"
            ).fetchall()
        ]
        pending_reviews = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE sent=0"
        ).fetchone()[0]
        unsent_messages = conn.execute(
            "SELECT COUNT(*) FROM customer_messages WHERE sent=0"
        ).fetchone()[0]
    return {
        "by_status": by_status,
        "needs_attention": needs_attention,
        "pending_reviews": pending_reviews,
        "unsent_messages": unsent_messages,
    }
