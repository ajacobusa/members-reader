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
    """Context-managed SQLite connection (WAL mode, 30s lock timeout, Row factory).

    Commits on clean exit and always closes; creates OUTPUT_DIR on first use.
    """
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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_email TEXT NOT NULL,
            customer_name TEXT,
            plan          TEXT DEFAULT 'monthly',
            start_date    TEXT,
            end_date      TEXT NOT NULL,          -- ISO date the subscription ends
            status        TEXT DEFAULT 'active',  -- active|expired|cancelled|renewed
            reminded_at   TEXT,                   -- last expiry reminder sent
            created_at    TEXT DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_reviews (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            rating       INTEGER NOT NULL,        -- 1..5
            text         TEXT,
            photo_url    TEXT,                     -- optional buyer photo
            listing      TEXT,
            verified     INTEGER DEFAULT 1,        -- a real, confirmed purchase
            published    INTEGER DEFAULT 1,        -- show on the site
            created_at   TEXT DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS catalog_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor      TEXT DEFAULT 'gelato',     -- gelato|printful|printify|manual|digital|...
            sku         TEXT,
            name        TEXT NOT NULL,
            category    TEXT,                       -- poster|canvas|framed|service|digital|...
            item_type   TEXT DEFAULT 'print',       -- print|service|digital
            cost        REAL DEFAULT 0,             -- your wholesale cost (0 for digital)
            price       REAL DEFAULT 0,             -- list price (optional)
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(vendor, sku, name)
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS misc_income (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel     TEXT DEFAULT 'affiliate',   -- affiliate|wholesale|other
            source      TEXT,                        -- program / partner name
            amount      REAL NOT NULL,               -- net income (e.g. commission)
            note        TEXT,
            day         TEXT DEFAULT (date('now')),
            created_at  TEXT DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ledger_snapshots (
            day        TEXT PRIMARY KEY,        -- ISO date
            revenue    REAL DEFAULT 0,
            cogs       REAL DEFAULT 0,          -- Gelato print cost
            etsy_fees  REAL DEFAULT 0,
            api_cost   REAL DEFAULT 0,          -- Claude
            opex       REAL DEFAULT 0,          -- prorated fixed overhead
            net_profit REAL DEFAULT 0,
            orders     INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_designs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            design_id   TEXT,                       -- client design id (per piece)
            order_id    TEXT,                       -- linked once an Etsy order arrives
            design_json TEXT,                       -- full layout: wording/colors/font/
                                                    -- size/position/rotation/photo fit
            summary     TEXT,                        -- human-readable order summary
            accepted    INTEGER DEFAULT 0,           -- customer pressed Accept
            accepted_at TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(email, design_id)
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS competitor_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            shop          TEXT NOT NULL,             -- competitor shop name/handle
            listings      INTEGER,                    -- active listing count
            min_price     REAL,                       -- lowest listing price seen
            avg_price     REAL,
            reviews       INTEGER,                    -- total shop reviews
            bestsellers   INTEGER,                    -- # listings with bestseller badge
            new_listings  INTEGER,                    -- new since last snapshot (optional)
            note          TEXT,
            captured_at   TEXT DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ab_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment  TEXT NOT NULL,             -- experiment key
            variant     TEXT NOT NULL,             -- variant key
            event       TEXT NOT NULL,             -- impression|conversion
            visitor     TEXT,                       -- anonymous client id
            created_at  TEXT DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            kind        TEXT NOT NULL,             -- referral|review|repeat_purchase
            points      INTEGER NOT NULL DEFAULT 0,
            ref         TEXT,                       -- order_id, referee email, etc.
            note        TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(email, kind, ref)
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS abandoned_customizations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL,
            listing       TEXT,                      -- listing title/number being designed
            material      TEXT,                      -- chosen format/frame
            size          TEXT,
            wording       TEXT,                      -- custom message in progress
            has_photo     INTEGER DEFAULT 0,         -- did they upload a photo
            state_json    TEXT,                      -- full client state (colors/font/etc)
            status        TEXT DEFAULT 'open',       -- open|recovered|converted|dismissed
            recovered_at  TEXT,                      -- last recovery email sent
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(email, listing)
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS winback_campaign (
            email      TEXT PRIMARY KEY,    -- lapsed customer
            stage      INTEGER DEFAULT 0,   -- last win-back stage sent (1/2/3)
            last_order_at TEXT,             -- their last order at send time (reset gate)
            sent_at    TEXT
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS gift_profiles (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_email   TEXT NOT NULL,            -- the buyer who saved this profile
            recipient_name TEXT NOT NULL,
            relationship  TEXT,                      -- Mom|Wife|Best Friend|...
            occasion      TEXT,                      -- Birthday|Anniversary|...
            event_date    TEXT,                      -- ISO date (MM-DD recurs yearly)
            notes         TEXT,                      -- room colors, favorite words, etc.
            last_order_id TEXT,                      -- most recent gift for this person
            reminded_at   TEXT,                      -- last reminder sent (idempotency)
            created_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(owner_email, recipient_name, occasion)
        );
        """)
        _migrate(conn)


def upsert_ledger_snapshot(day: str, row: dict) -> None:
    """Insert or replace the daily ledger snapshot for `day` (idempotent per day)."""
    with _conn() as conn:
        conn.execute("""
            INSERT INTO ledger_snapshots
              (day, revenue, cogs, etsy_fees, api_cost, opex, net_profit, orders, updated_at)
            VALUES (?,?,?,?,?,?,?,?, datetime('now'))
            ON CONFLICT(day) DO UPDATE SET
              revenue=excluded.revenue, cogs=excluded.cogs, etsy_fees=excluded.etsy_fees,
              api_cost=excluded.api_cost, opex=excluded.opex,
              net_profit=excluded.net_profit, orders=excluded.orders,
              updated_at=datetime('now')
        """, (day, row.get("revenue", 0), row.get("cogs", 0), row.get("etsy_fees", 0),
              row.get("api_cost", 0), row.get("opex", 0), row.get("net_profit", 0),
              row.get("orders", 0)))


def get_ledger_snapshots(limit: int = 90) -> list[dict]:
    """Return the most recent daily ledger snapshots, newest day first."""
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM ledger_snapshots ORDER BY day DESC LIMIT ?", (limit,))]


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
    if "channel" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN channel TEXT DEFAULT 'etsy'")
    if "vendor" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN vendor TEXT DEFAULT 'gelato'")
    if "product_type" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN product_type TEXT DEFAULT 'print'")
    # Profit-optimization dimensions (nullable; populated as orders capture them).
    if "material" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN material TEXT")
    if "size" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN size TEXT")
    if "listing" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN listing TEXT")
    if "acquisition_source" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN acquisition_source TEXT")
    # Customer print file + AI quality decision (approve|hold|reject).
    if "print_file" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN print_file TEXT")
    if "print_quality" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN print_quality TEXT")
    # Fulfillment timestamps for the production-capacity monitor.
    if "shipped_at" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN shipped_at TEXT")
    if "delivered_at" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN delivered_at TEXT")
    # Honestly-named vendor order id (gelato_order_id historically held the id
    # for EVERY vendor); backfilled so old orders keep tracking.
    if "vendor_order_id" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN vendor_order_id TEXT")
    conn.execute(
        "UPDATE orders SET vendor_order_id = gelato_order_id "
        "WHERE (vendor_order_id IS NULL OR vendor_order_id = '') "
        "AND gelato_order_id IS NOT NULL AND gelato_order_id != ''")
    # SHA-256 of the print file at customer-approval time - the parity gate
    # proving the approved proof IS the file sent to production.
    if "proof_file_hash" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN proof_file_hash TEXT")
    # The basket as recorded at checkout: structured line items (JSON) + the
    # total item count, so the order's COUNT and PRICE can be reconciled
    # against fulfillment and the ledger (a multi-line basket is no longer
    # flattened to one untyped row).
    if "line_items" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN line_items TEXT")
    if "item_count" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN item_count INTEGER")
    # Delivery validation: 1 = carrier/vendor CONFIRMED delivery, 0 = assumed
    # by the post-ship timer (Printify/Printful never report delivery).
    if "delivery_confirmed" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN delivery_confirmed INTEGER DEFAULT 0")
    # 1 once the buyer has been sent the shipped/tracking notification - so a
    # failed push retries next run instead of being lost forever.
    if "buyer_notified" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN buyer_notified INTEGER DEFAULT 0")
    # Destination + shipping economics for the shipping-variance / profit-by-
    # destination audit (catch silent margin leakage on far/heavy shipments).
    for _col in ("country", "state"):
        if _col not in cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {_col} TEXT")
    for _col in ("shipping_cost", "shipping_collected"):
        if _col not in cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {_col} REAL")
    # Carrier name helps the tracking API confirm real delivery; the estimated
    # delivery date (from Gelato/carrier) sets buyer expectations + SLA checks.
    if "carrier" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN carrier TEXT")
    if "estimated_delivery" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN estimated_delivery TEXT")
    # Delivery integrity: a 'delivered' order is NOT automatically problem-free.
    #   delivery_disputed         : a case/refund/complaint arrived after delivery
    #   do_not_request_review     : owner says never ask this buyer for a review
    #   manual_delivery_confirmed : owner-confirmed delivery (counts as confirmed)
    for _col in ("delivery_disputed", "do_not_request_review",
                 "manual_delivery_confirmed"):
        if _col not in cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {_col} INTEGER DEFAULT 0")
    # ACTUAL Etsy financials (from the receipt / Orders CSV) - real tax, fees,
    # and net payout instead of estimates. Null until imported.
    if "tax_collected" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN tax_collected REAL")
    if "etsy_fees_actual" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN etsy_fees_actual REAL")
    if "net_payout" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN net_payout REAL")
    # Recovery escalation stage (0=none,1=1h,2=24h,3=72h sent) for abandoned
    # customizations - so the recovery email escalates instead of firing once.
    accols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(abandoned_customizations)")}
    if accols and "recovery_stage" not in accols:
        conn.execute("ALTER TABLE abandoned_customizations "
                     "ADD COLUMN recovery_stage INTEGER DEFAULT 0")


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
             sale_price, gelato_cost, channel, vendor, product_type,
             material, size, listing, acquisition_source,
             line_items, item_count, country, state,
             shipping_cost, shipping_collected)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            data.get("channel", "etsy"),
            data.get("vendor", "gelato"),
            data.get("product_type", "print"),
            data.get("material"),
            data.get("size"),
            data.get("listing"),
            data.get("acquisition_source"),
            data.get("line_items"),
            data.get("item_count"),
            data.get("country"),
            data.get("state"),
            data.get("shipping_cost"),
            data.get("shipping_collected"),
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
    """Fetch a single order by its internal order_id, or None if absent."""
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
    """Return all orders with the given status, newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE status=? ORDER BY created_at DESC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_orders(limit: int = 100) -> list[dict]:
    """Return up to `limit` orders, newest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def log_pipeline_stage(order_id: str, stage: str, status: str, message: str = "") -> None:
    """Append a pipeline stage event (stage, status, message) for an order."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO pipeline_log (order_id, stage, status, message) VALUES (?,?,?,?)",
            (order_id, stage, status, message),
        )


def get_pipeline_log(order_id: str) -> list[dict]:
    """Return an order's pipeline events in chronological order."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pipeline_log WHERE order_id=? ORDER BY created_at",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Product CRUD ─────────────────────────────────────────────────

def upsert_product(data: dict) -> None:
    """Insert or replace a product row keyed by product_id."""
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
    """Return active products in a category."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM products WHERE category=? AND active=1", (category,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Template CRUD ─────────────────────────────────────────────────

def upsert_template(data: dict) -> None:
    """Insert or replace a design template row keyed by template_id."""
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
    """Return active templates matching a scenery type."""
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
    """Return an order's customer messages in chronological order."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM customer_messages WHERE order_id=? ORDER BY created_at",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_message_sent(message_id: int) -> None:
    """Flag a customer message as sent."""
    with _conn() as conn:
        conn.execute("UPDATE customer_messages SET sent=1 WHERE id=?", (message_id,))


# ── Upsell persistence ───────────────────────────────────────────

def save_upsell(order_id: str, offer_type: str, offer_body: str) -> int:
    """Persist an upsell offer for an order. Returns the new row id."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO upsells (order_id, offer_type, offer_body) VALUES (?,?,?)",
            (order_id, offer_type, offer_body),
        )
        return cur.lastrowid


def get_upsells(order_id: str) -> list[dict]:
    """Return an order's upsell offers in chronological order."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM upsells WHERE order_id=? ORDER BY created_at", (order_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── Review persistence ───────────────────────────────────────────

def save_review(order_id: str, review_message: str, scheduled_for: str = "") -> int:
    """Persist a review-request message (optionally scheduled). Returns the row id."""
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
    """Flag a review-request message as sent."""
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
    """Return all mailing-list subscribers, newest first."""
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM subscribers ORDER BY created_at DESC")]


def subscriber_count() -> int:
    """Return the total number of mailing-list subscribers."""
    with _conn() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM subscribers").fetchone()["n"]


# ── Saved designs (customer layout preferences) ─────────────────

def save_design(email: str, design_json: str = "", design_id: str = "",
                summary: str = "", order_id: str = "") -> int:
    """Save/update a customer's design layout. Keyed by email + design_id."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return 0
    design_id = (design_id or "default").strip()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO saved_designs
               (email, design_id, order_id, design_json, summary)
               VALUES (?,?,?,?,?)
               ON CONFLICT(email, design_id) DO UPDATE SET
                 design_json=excluded.design_json, summary=excluded.summary,
                 order_id=COALESCE(NULLIF(excluded.order_id,''), order_id),
                 updated_at=datetime('now')""",
            (email, design_id, order_id, design_json, summary))
        return cur.lastrowid or 0


def accept_design(email: str, design_id: str = "default") -> None:
    """Mark a saved design as customer-accepted, stamping accepted_at."""
    from datetime import datetime as _dt
    with _conn() as conn:
        conn.execute(
            "UPDATE saved_designs SET accepted=1, accepted_at=?, updated_at=? "
            "WHERE email=? AND design_id=?",
            (_dt.now().isoformat(), _dt.now().isoformat(),
             (email or "").strip().lower(), design_id))


def get_designs(email: str = "") -> list[dict]:
    """Return saved designs (all, or one customer's), most recently updated first."""
    with _conn() as conn:
        if email:
            rows = conn.execute(
                "SELECT * FROM saved_designs WHERE email=? ORDER BY updated_at DESC",
                (email.strip().lower(),))
        else:
            rows = conn.execute("SELECT * FROM saved_designs ORDER BY updated_at DESC")
        return [dict(r) for r in rows]


# ── Competitor snapshots (intelligence) ─────────────────────────

def add_competitor_snapshot(shop: str, listings: int = None, min_price: float = None,
                            avg_price: float = None, reviews: int = None,
                            bestsellers: int = None, new_listings: int = None,
                            note: str = "") -> int:
    """Record a point-in-time snapshot of a competitor shop."""
    shop = (shop or "").strip()
    if not shop:
        return 0
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO competitor_snapshots
               (shop, listings, min_price, avg_price, reviews, bestsellers,
                new_listings, note)
               VALUES (?,?,?,?,?,?,?,?)""",
            (shop, listings, min_price, avg_price, reviews, bestsellers,
             new_listings, note))
        return cur.lastrowid or 0


def get_competitor_snapshots(shop: str = "") -> list[dict]:
    """Return competitor snapshots (all shops, or one), oldest first for diffing."""
    with _conn() as conn:
        if shop:
            rows = conn.execute(
                "SELECT * FROM competitor_snapshots WHERE shop=? "
                "ORDER BY captured_at ASC", (shop,))
        else:
            rows = conn.execute(
                "SELECT * FROM competitor_snapshots ORDER BY captured_at ASC")
        return [dict(r) for r in rows]


# ── A/B testing events ──────────────────────────────────────────

def record_ab_event(experiment: str, variant: str, event: str,
                    visitor: str = "") -> int:
    """Record an A/B impression or conversion."""
    experiment = (experiment or "").strip()
    variant = (variant or "").strip()
    if not experiment or not variant or event not in ("impression", "conversion"):
        return 0
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO ab_events (experiment, variant, event, visitor) "
            "VALUES (?,?,?,?)", (experiment, variant, event, visitor))
        return cur.lastrowid or 0


def get_ab_events(experiment: str = "") -> list[dict]:
    """Return A/B events, optionally filtered to one experiment."""
    with _conn() as conn:
        if experiment:
            rows = conn.execute(
                "SELECT * FROM ab_events WHERE experiment=?", (experiment,))
        else:
            rows = conn.execute("SELECT * FROM ab_events")
        return [dict(r) for r in rows]


# ── Rewards / referrals (loyalty points ledger) ─────────────────

def add_reward(email: str, kind: str, points: int, ref: str = "",
               note: str = "") -> int:
    """Record a loyalty/referral event. Idempotent on (email, kind, ref)."""
    email = (email or "").strip().lower()
    if "@" not in email or kind not in ("referral", "review", "repeat_purchase"):
        return 0
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO rewards (email, kind, points, ref, note)
               VALUES (?,?,?,?,?)
               ON CONFLICT(email, kind, ref) DO NOTHING""",
            (email, kind, int(points), ref, note))
        return cur.lastrowid or 0


def get_rewards(email: str = "") -> list[dict]:
    """Return loyalty/referral reward rows (all, or one customer's), newest first."""
    with _conn() as conn:
        if email:
            rows = conn.execute(
                "SELECT * FROM rewards WHERE email=? ORDER BY created_at DESC",
                (email.strip().lower(),))
        else:
            rows = conn.execute("SELECT * FROM rewards ORDER BY created_at DESC")
        return [dict(r) for r in rows]


# ── Abandoned customizations (recovery) ─────────────────────────

def save_customization(email: str, listing: str = "", material: str = "",
                       size: str = "", wording: str = "", has_photo: bool = False,
                       state_json: str = "") -> int:
    """Upsert an in-progress (abandoned) customization keyed by email+listing."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return 0
    # Local-time stamp (matches update_order et al.) so the recovery age check
    # isn't skewed by SQLite datetime('now') being UTC.
    _ts = datetime.now().isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO abandoned_customizations
               (email, listing, material, size, wording, has_photo, state_json,
                status, updated_at)
               VALUES (?,?,?,?,?,?,?, 'open', ?)
               ON CONFLICT(email, listing) DO UPDATE SET
                 material=excluded.material, size=excluded.size,
                 wording=excluded.wording, has_photo=excluded.has_photo,
                 state_json=excluded.state_json,
                 status=CASE WHEN abandoned_customizations.status='converted'
                             THEN 'converted' ELSE 'open' END,
                 updated_at=excluded.updated_at
            """,
            (email, listing, material, size, wording, 1 if has_photo else 0,
             state_json, _ts))
        return cur.lastrowid or 0


def get_open_customizations(older_than_minutes: int = 0) -> list[dict]:
    """Open abandoned customizations, optionally only those idle for N minutes."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM abandoned_customizations WHERE status='open' "
            "ORDER BY updated_at DESC")
        items = [dict(r) for r in rows]
    if older_than_minutes <= 0:
        return items
    from datetime import datetime as _dt, timedelta as _td
    cutoff = _dt.now() - _td(minutes=older_than_minutes)
    out = []
    for it in items:
        try:
            upd = _dt.fromisoformat((it.get("updated_at") or "").replace("Z", ""))
        except ValueError:
            continue
        if upd <= cutoff:
            out.append(it)
    return out


def get_winback_state(email: str) -> dict:
    """The customer's win-back campaign state ({stage, last_order_at}), or empty."""
    email = (email or "").strip().lower()
    with _conn() as conn:
        row = conn.execute(
            "SELECT stage, last_order_at FROM winback_campaign WHERE email=?",
            (email,)).fetchone()
    return dict(row) if row else {"stage": 0, "last_order_at": ""}


def set_winback_stage(email: str, stage: int, last_order_at: str) -> None:
    """Record that win-back `stage` was sent for a customer whose last order was
    `last_order_at` (so a NEW order - a different last_order_at - resets them)."""
    email = (email or "").strip().lower()
    from datetime import datetime as _dt
    with _conn() as conn:
        conn.execute(
            "INSERT INTO winback_campaign (email, stage, last_order_at, sent_at) "
            "VALUES (?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
            "stage=excluded.stage, last_order_at=excluded.last_order_at, "
            "sent_at=excluded.sent_at",
            (email, stage, last_order_at, _dt.now().isoformat()))


def advance_recovery_stage(email: str, listing: str, stage: int) -> None:
    """Record that recovery `stage` (1=1h,2=24h,3=72h) was sent for an
    abandoned customization, stamping recovered_at."""
    email = (email or "").strip().lower()
    from datetime import datetime as _dt
    with _conn() as conn:
        conn.execute(
            "UPDATE abandoned_customizations SET recovery_stage=?, recovered_at=? "
            "WHERE email=? AND listing=?",
            (stage, _dt.now().isoformat(), email, listing))


def mark_customization(email: str, listing: str, status: str,
                       recovered: bool = False) -> None:
    """Set an abandoned customization's status; `recovered` also stamps recovered_at."""
    email = (email or "").strip().lower()
    from datetime import datetime as _dt
    with _conn() as conn:
        if recovered:
            conn.execute(
                "UPDATE abandoned_customizations SET status=?, recovered_at=? "
                "WHERE email=? AND listing=?",
                (status, _dt.now().isoformat(), email, listing))
        else:
            conn.execute(
                "UPDATE abandoned_customizations SET status=? "
                "WHERE email=? AND listing=?", (status, email, listing))


# ── Gift profiles (memory-based repeat gifting) ──────────────────

def save_gift_profile(owner_email: str, recipient_name: str,
                      relationship: str = "", occasion: str = "",
                      event_date: str = "", notes: str = "",
                      last_order_id: str = "") -> int:
    """Create/update a saved gift profile. Keyed by owner+recipient+occasion."""
    owner_email = (owner_email or "").strip().lower()
    recipient_name = (recipient_name or "").strip()
    if not owner_email or not recipient_name:
        return 0
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO gift_profiles
               (owner_email, recipient_name, relationship, occasion, event_date,
                notes, last_order_id)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(owner_email, recipient_name, occasion) DO UPDATE SET
                 relationship=excluded.relationship,
                 event_date=excluded.event_date,
                 notes=excluded.notes,
                 last_order_id=COALESCE(NULLIF(excluded.last_order_id,''), last_order_id)
            """,
            (owner_email, recipient_name, relationship, occasion, event_date,
             notes, last_order_id))
        return cur.lastrowid or 0


def get_gift_profiles(owner_email: str = "") -> list[dict]:
    """Return saved gift profiles (all, or one buyer's), newest first."""
    with _conn() as conn:
        if owner_email:
            rows = conn.execute(
                "SELECT * FROM gift_profiles WHERE owner_email=? ORDER BY created_at DESC",
                (owner_email.strip().lower(),))
        else:
            rows = conn.execute(
                "SELECT * FROM gift_profiles ORDER BY created_at DESC")
        return [dict(r) for r in rows]


def mark_profile_reminded(profile_id: int, when: str = "") -> None:
    """Stamp reminded_at on a gift profile (idempotency guard for reminders)."""
    from datetime import datetime as _dt
    with _conn() as conn:
        conn.execute("UPDATE gift_profiles SET reminded_at=? WHERE id=?",
                     (when or _dt.now().isoformat(), profile_id))


# ── Customer reviews (real, verified - shown on the site) ────────

def add_review(customer_name: str, rating: int, text: str = "",
               photo_url: str = "", listing: str = "", verified: bool = True,
               published: bool = True) -> int:
    """Store a verified customer review (rating clamped to 1..5). Returns the row id."""
    rating = max(1, min(5, int(rating)))
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO customer_reviews
               (customer_name, rating, text, photo_url, listing, verified, published)
               VALUES (?,?,?,?,?,?,?)""",
            (customer_name, rating, text, photo_url, listing,
             1 if verified else 0, 1 if published else 0))
        return cur.lastrowid


def get_published_reviews(limit: int = 50) -> list[dict]:
    """Return up to `limit` published customer reviews, newest first."""
    with _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM customer_reviews WHERE published=1 "
            "ORDER BY created_at DESC LIMIT ?", (limit,))]


def review_stats() -> dict:
    """Return count and average rating of published reviews."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) n, AVG(rating) a FROM customer_reviews WHERE published=1"
        ).fetchone()
    n = row["n"] or 0
    return {"count": n, "avg": round(row["a"], 1) if n else 0.0}


# ── Multi-vendor catalog (products & services from any vendor) ───

def add_catalog_item(name: str, vendor: str = "gelato", sku: str = "",
                     category: str = "", item_type: str = "print",
                     cost: float = 0.0, price: float = 0.0) -> int:
    """Add a catalog item; duplicates on (vendor, sku, name) are ignored."""
    with _conn() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO catalog_items
               (vendor, sku, name, category, item_type, cost, price)
               VALUES (?,?,?,?,?,?,?)""",
            (vendor, sku, name, category, item_type, cost, price))
        return cur.lastrowid


def get_catalog_items(vendor: str = "", active_only: bool = True) -> list[dict]:
    """Return catalog items, optionally filtered by vendor and/or active flag."""
    q, args = "SELECT * FROM catalog_items WHERE 1=1", []
    if vendor:
        q += " AND vendor=?"; args.append(vendor)
    if active_only:
        q += " AND active=1"
    q += " ORDER BY vendor, category, name"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, args)]


def set_catalog_item_active(item_id: int, active: bool) -> None:
    """Activate or deactivate a catalog item."""
    with _conn() as conn:
        conn.execute("UPDATE catalog_items SET active=? WHERE id=?",
                     (1 if active else 0, item_id))


# ── Misc income (affiliate commissions, wholesale, other) ────────

def add_income(amount: float, channel: str = "affiliate", source: str = "",
               note: str = "", day: str = "") -> int:
    """Record a miscellaneous income entry (defaults to today). Returns the row id."""
    from datetime import date as _date
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO misc_income (channel, source, amount, note, day) VALUES (?,?,?,?,?)",
            (channel, source, amount, note, day or _date.today().isoformat()))
        return cur.lastrowid


def get_income(since_iso: str = "", until_iso: str = "") -> list[dict]:
    """Return misc income rows in [since, until] by day (both bounds optional)."""
    q, args = "SELECT * FROM misc_income WHERE 1=1", []
    if since_iso:
        q += " AND day >= ?"; args.append(since_iso)
    if until_iso:
        q += " AND day <= ?"; args.append(until_iso)
    q += " ORDER BY day"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, args)]


# ── Subscriptions (memberships / recurring plans) ────────────────

def add_subscription(customer_email: str, end_date: str, customer_name: str = "",
                     plan: str = "monthly", start_date: str = "") -> int:
    """Create a subscription record (email lowercased). Returns the row id."""
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO subscriptions
               (customer_email, customer_name, plan, start_date, end_date)
               VALUES (?,?,?,?,?)""",
            ((customer_email or "").strip().lower(), customer_name, plan,
             start_date, end_date))
        return cur.lastrowid


def get_subscriptions(status: str = "") -> list[dict]:
    """Return subscriptions (optionally by status), soonest end_date first."""
    q = "SELECT * FROM subscriptions"
    args: tuple = ()
    if status:
        q += " WHERE status=?"
        args = (status,)
    q += " ORDER BY end_date ASC"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, args)]


def get_expiring_subscriptions(within_days: int = 7) -> list[dict]:
    """Active subscriptions ending within `within_days` (incl. already past),
    that haven't been reminded for this end_date yet."""
    from datetime import date, timedelta
    cutoff = (date.today() + timedelta(days=within_days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM subscriptions
               WHERE status='active' AND date(end_date) <= date(?)
               ORDER BY end_date ASC""", (cutoff,))
        # Only those not yet reminded (reset reminded_at on renewal to re-enable).
        return [dict(r) for r in rows if not dict(r).get("reminded_at")]


def mark_subscription_reminded(sub_id: int) -> None:
    """Stamp reminded_at on a subscription so expiry reminders send only once."""
    from datetime import datetime
    with _conn() as conn:
        conn.execute("UPDATE subscriptions SET reminded_at=? WHERE id=?",
                     (datetime.now().isoformat(timespec="seconds"), sub_id))


def set_subscription_status(sub_id: int, status: str) -> None:
    """Update a subscription's status (active|expired|cancelled|renewed)."""
    with _conn() as conn:
        conn.execute("UPDATE subscriptions SET status=? WHERE id=?", (status, sub_id))


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
    """Return approvals still awaiting a human decision, oldest first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def get_approval(approval_id: int) -> Optional[dict]:
    """Fetch a single approval row by id, or None if absent."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM approvals WHERE id=?",
                           (approval_id,)).fetchone()
        return dict(row) if row else None


def resolve_approval(approval_id: int, status: str,
                     decided_by: str = "owner") -> None:
    """Record the decision on an approval (approved/rejected), stamping decided_at."""
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
    """Log an API usage cost row (provider, tokens/units, USD). Returns the row id."""
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
