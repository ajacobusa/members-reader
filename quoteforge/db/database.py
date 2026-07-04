"""SQLite database — local mirror of Airtable. Products / Orders / Templates tables."""
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from quoteforge.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

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
        # Customer registry - the source of truth that a customer_id is UNIQUE in every
        # case: customer_id is the PRIMARY KEY (no two customers share one) and email is
        # UNIQUE (one id per buyer, so it stays stable across their orders).
        conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            email       TEXT UNIQUE,
            name        TEXT,
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
        # Official product images per SKU (#181): the studio/lifestyle/mockup shots
        # synced from the connected store's template-created listings. Idempotent on
        # (sku, uid, rank) so a daily re-sync refreshes a row instead of duplicating.
        conn.execute("""
        CREATE TABLE IF NOT EXISTS gelato_product_images (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            gelato_sku         TEXT NOT NULL,
            gelato_product_uid TEXT DEFAULT '',
            etsy_listing_id    TEXT DEFAULT '',
            etsy_image_id      TEXT DEFAULT '',
            image_url          TEXT NOT NULL,
            image_rank         INTEGER DEFAULT 0,
            image_type         TEXT DEFAULT 'mockup',
            source             TEXT DEFAULT 'gelato_ecommerce',
            is_active          INTEGER DEFAULT 1,
            last_seen_at       TEXT DEFAULT (datetime('now')),
            created_at         TEXT DEFAULT (datetime('now')),
            UNIQUE(gelato_sku, gelato_product_uid, image_rank)
        );
        """)
        # Uptime heartbeat (#182): one row per run of each daily automation job, so a
        # job that silently STOPPED running (or keeps failing) is detectable/alertable
        # - the core high-availability signal ("did the critical job actually run + ok").
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_runs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            job       TEXT NOT NULL,
            ran_at    TEXT DEFAULT (datetime('now')),
            ok        INTEGER DEFAULT 1,
            detail    TEXT DEFAULT ''
        );
        """)
        # Audit trail (#182-P2): an append-only record of SENSITIVE / privileged
        # actions - an admin overriding a customer-approved order lock, a manual
        # official-image override, etc. The record is what makes those actions
        # accountable after the fact (the update_order docstring already promises an
        # "audited admin override"; this is where that promise is kept).
        conn.execute("""
        CREATE TABLE IF NOT EXISTS security_events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            at        TEXT DEFAULT (datetime('now')),
            event     TEXT NOT NULL,
            actor     TEXT DEFAULT 'system',
            detail    TEXT DEFAULT ''
        );
        """)
        _migrate(conn)
        # Indexes for the frequent lookups (additive; etsy_order_id is already
        # covered by its UNIQUE constraint). Keeps status filters + child-table
        # joins off full scans as the tables grow.
        for _idx, _tbl, _col in (
            ("idx_orders_status", "orders", "status"),
            # Ownership / customer-history lookups (the /upload IDOR guard, buyer
            # order lists) and vendor-order reconciliation (order_monitor) scanned
            # the whole table; index their lookup columns.
            ("idx_orders_email", "orders", "customer_email"),
            ("idx_orders_gelato", "orders", "gelato_order_id"),
            ("idx_pipeline_log_order", "pipeline_log", "order_id"),
            ("idx_customer_messages_order", "customer_messages", "order_id"),
            # Resume-your-design lookups by email (storefront draft restore).
            ("idx_saved_designs_email", "saved_designs", "email"),
            # Official-image lookup by SKU (the storefront tile hot path, #181).
            ("idx_gpi_sku", "gelato_product_images", "gelato_sku"),
        ):
            try:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {_idx} ON {_tbl}({_col})")
            except sqlite3.OperationalError as exc:
                # table not present in an older snapshot - safe to skip, but log it
                logger.debug("index %s skipped (%s not present?): %s", _idx, _tbl, exc)


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
    # Apparel variants carry a colour (NULL for wall art, which has none).
    if "color" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN color TEXT")
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
    # Path to the saved PDF of the on-screen approved proof - the final approval
    # evidence, stored under the order id and NEVER emailed to the customer.
    if "proof_pdf" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN proof_pdf TEXT")
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
    # The Gelato shipment method this order ships by (e.g. 'express' when the buyer
    # chose the paid express upgrade); blank/NULL = the normal/default method.
    if "shipment_method" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN shipment_method TEXT")
    # Carrier name helps the tracking API confirm real delivery; the estimated
    # delivery date (from Gelato/carrier) sets buyer expectations + SLA checks.
    if "carrier" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN carrier TEXT")
    if "estimated_delivery" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN estimated_delivery TEXT")
    # Durable fulfillment retry: how many times the scheduled retry job has
    # re-attempted a previously-errored submission. Bounds futile retries on a
    # permanent failure (bad product UID) while recovering from a transient outage.
    if "fulfillment_retries" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN fulfillment_retries "
                     "INTEGER DEFAULT 0")
    # Units of THIS product ordered (distinct from item_count = basket size). It must
    # reach the supplier submission or a qty>1 order ships only one unit.
    if "quantity" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN quantity INTEGER DEFAULT 1")
    # Stable per-buyer id (derived from the buyer email/name) so orders can be grouped
    # by customer for support + repeat-buyer analytics; assigned at create_order.
    if "customer_id" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN customer_id TEXT")
    # Owner per-order notices: 1 once the INVOICE (on placement) / SHIPPED+tracking
    # (on ship) email has been sent to ORDER_NOTIFY_EMAIL - so a retry/re-poll never
    # double-sends, and a failed send retries next run instead of being lost.
    for _col in ("owner_invoice_emailed", "owner_shipped_emailed",
                 "owner_delivered_emailed"):
        if _col not in cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {_col} INTEGER DEFAULT 0")
    # Delivery integrity: a 'delivered' order is NOT automatically problem-free.
    #   delivery_disputed         : a case/refund/complaint arrived after delivery
    #   do_not_request_review     : owner says never ask this buyer for a review
    #   manual_delivery_confirmed : owner-confirmed delivery (counts as confirmed)
    for _col in ("delivery_disputed", "do_not_request_review",
                 "manual_delivery_confirmed"):
        if _col not in cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {_col} INTEGER DEFAULT 0")
    # Gelato claim tracking (defect/damage/loss -> reprint via Report Problem).
    #   claim_status     : staged | filed | approved | rejected
    #   claim_category   : the resolution-engine issue category claimed
    #   claim_filed_at   : ISO timestamp the claim was staged/filed
    #   claim_resolution : Gelato's verdict text once it replies
    #   claim_needs_admin: "1" when a covered claim is past the 7-day customer
    #                      window but still inside the supplier window (held for
    #                      an admin decision, NOT a missing-evidence hold)
    for _col in ("claim_status", "claim_category", "claim_filed_at",
                 "claim_resolution", "claim_photos", "ship_to",
                 "replacement_order_id", "claim_needs_admin"):
        if _col not in cols:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {_col} TEXT")
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

def _derive_customer_id(email: str, name: str = "") -> str:
    """The BASE per-buyer id from the buyer's email (or name) - same buyer -> same base,
    so orders group by customer. 'CUST-' + 10 hex of a sha1; 'CUST-anon' if nothing
    given. get_or_create_customer guarantees the FINAL id is globally unique."""
    import hashlib
    key = (email or "").strip().lower() or (name or "").strip().lower()
    if not key:
        return "CUST-anon"
    return "CUST-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def get_or_create_customer(email: str, name: str = "", anon_key: str = "") -> str:
    """Return a customer_id that is UNIQUE in every case, backed by the `customers`
    registry (customer_id PRIMARY KEY, email UNIQUE):
      - same email  -> the SAME id every time (stable grouping);
      - different emails -> always DIFFERENT ids (a base-hash collision is disambiguated
        with a numeric suffix until unique);
      - no email -> a per-buyer-unique anon id derived from anon_key (e.g. the order id),
        so anonymous orders are never collapsed onto one shared id.
    """
    import hashlib
    email_n = (email or "").strip().lower()
    with _conn() as conn:
        if email_n:
            row = conn.execute("SELECT customer_id FROM customers WHERE email=?",
                               (email_n,)).fetchone()
            if row:
                return row["customer_id"]
            base = _derive_customer_id(email_n)
        else:
            # No email: unique per order (anon_key is the unique order id).
            seed = (anon_key or "").strip() or "anon"
            base = "CUST-anon-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
        # Guarantee global uniqueness of the id itself (disambiguate any collision).
        cid, n = base, 1
        while conn.execute("SELECT 1 FROM customers WHERE customer_id=?",
                           (cid,)).fetchone():
            n += 1
            cid = f"{base}-{n}"
        try:
            conn.execute("INSERT INTO customers (customer_id, email, name) VALUES (?,?,?)",
                         (cid, email_n or None, name or None))
        except sqlite3.IntegrityError:
            # A concurrent insert won the race for this email - return the stored id.
            row = conn.execute("SELECT customer_id FROM customers WHERE email=?",
                               (email_n,)).fetchone()
            if row:
                return row["customer_id"]
            raise
        return cid


def create_order(data: dict) -> str:
    """Insert a new order. Returns order_id."""
    order_id = data.get("order_id") or f"QF-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:18]}"
    # Resolve a globally-unique customer_id BEFORE opening the order write connection
    # (get_or_create_customer uses its own connection - don't nest SQLite writers).
    cust_id = data.get("customer_id") or get_or_create_customer(
        data.get("customer_email", ""), data.get("customer_name", ""), order_id)
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO orders
            (order_id, etsy_order_id, customer_name, customer_email,
             recipient_name, sender_name, relationship, occasion,
             scenery, tone, memory, output_style, status,
             sale_price, gelato_cost, channel, vendor, product_type,
             material, size, color, listing, acquisition_source,
             line_items, item_count, country, state,
             shipping_cost, shipping_collected, shipment_method, quantity,
             customer_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
            data.get("color"),
            data.get("listing"),
            data.get("acquisition_source"),
            data.get("line_items"),
            data.get("item_count"),
            data.get("country"),
            data.get("state"),
            data.get("shipping_cost"),
            data.get("shipping_collected"),
            data.get("shipment_method"),
            int(data.get("quantity") or 1),
            cust_id,
            # Stamp created_at in the shop's LOCAL time so monthly financials/taxes
            # attribute an order to the local calendar month. The SQLite default is UTC,
            # which mis-files an order created late on the last local day of a month into
            # the NEXT month. Explicit local time fixes that for new + existing DBs.
            data.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
    # Attach the customer's most-recent confirmed design (incl. any 12-month calendar
    # photo URLs) to this order, so the personalization travels with it to production.
    try:
        link_design_to_order(data.get("customer_email", ""), order_id)
    except Exception as exc:  # noqa: BLE001 - never block an order, but never silent:
        # a failed link means the personalization/design may not reach production.
        logger.warning("link_design_to_order failed for %s: %s", order_id, exc)
    return order_id


# Customer-approved design fields that LOCK once the customer approves the proof.
# After approval these print exactly as shown and must not change silently - an
# edit would ship a defective/mis-personalized item. Status, tracking, claim,
# shipping-address, vendor-id and proof fields stay writable (the lifecycle and
# fulfilment must keep advancing).
LOCKED_FIELDS = frozenset({
    "recipient_name", "sender_name", "relationship", "occasion", "scenery",
    "tone", "memory", "output_style", "generated_quote", "size", "material",
    "color",   # apparel colour is part of the approved proof - immutable after
})


class OrderLockedError(Exception):
    """Raised when an attempt is made to edit a locked field on an approved order."""


def update_order(order_id: str, *, allow_locked: bool = False, **fields) -> None:
    """Update specific fields on an order.

    Once the customer has approved the proof (``proof_approved`` set), the
    locked design fields (see ``LOCKED_FIELDS``) are immutable: a write that
    would CHANGE one to a new value raises ``OrderLockedError``. Re-writing the
    same value is a no-op and allowed. An audited admin edit can pass
    ``allow_locked=True`` to override the lock.
    """
    touched = LOCKED_FIELDS & set(fields)
    if touched:
        current = get_order(order_id)
        if current and current.get("proof_approved"):
            # None and "" are equivalent "empty"; compare as strings so a
            # re-write of the same value is a no-op rather than a false lock hit.
            _norm = lambda v: "" if v is None else str(v)
            changed = [k for k in sorted(touched)
                       if _norm(fields[k]) != _norm(current.get(k))]
            if changed:
                if not allow_locked:
                    raise OrderLockedError(
                        f"order {order_id} is locked after customer approval; "
                        f"cannot edit {', '.join(changed)} "
                        f"(pass allow_locked=True for an audited admin override)")
                # allow_locked=True is a PRIVILEGED override of a customer-approved
                # order -> audit it (#182-P2), keeping the docstring's promise.
                record_security_event(
                    "order_lock_override", actor="admin",
                    detail=f"order={order_id} fields={changed}")
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


def existing_listing_id(gelato_sku: str, template_id: str = "") -> str:
    """The Etsy listing id already mapped to (gelato_sku[, template_id]), or "".
    The dedupe key for listing-create: a caller checks this BEFORE POSTing so a
    re-run reuses the existing listing instead of creating a duplicate (#182)."""
    gelato_sku = (gelato_sku or "").strip()
    if not gelato_sku:
        return ""
    q = ("SELECT etsy_listing_id FROM products WHERE gelato_sku=? "
         "AND etsy_listing_id IS NOT NULL AND etsy_listing_id!=''")
    args = [gelato_sku]
    if template_id:
        q += " AND template_id=?"
        args.append(template_id)
    q += " LIMIT 1"
    with _conn() as conn:
        row = conn.execute(q, args).fetchone()
        return (row[0] if row else "") or ""


def orphan_products() -> list[dict]:
    """ACTIVE products that are mapped to fulfillment (a gelato_sku) but have NO Etsy
    listing linked (etsy_listing_id NULL/empty) — i.e. a sellable product that was
    never published, so a customer can't actually buy it (#182-P0b). The auto-link
    write path (create_draft_listing -> upsert_product) is what CLEARS these; this
    detector is the visibility side so a stuck/never-published product doesn't hide.
    Returns [{product_id, gelato_sku, title}]; empty when every active product is
    linked (or none exist yet)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT product_id, gelato_sku, title FROM products "
            "WHERE active=1 AND gelato_sku IS NOT NULL AND gelato_sku!='' "
            "AND (etsy_listing_id IS NULL OR TRIM(etsy_listing_id)='') "
            "ORDER BY product_id").fetchall()
        return [dict(r) for r in rows]


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


def pending_customer_messages(types: tuple) -> list[dict]:
    """Unsent customer messages of the given types, joined with the buyer's email
    (for the transactional auto-notifier). Skips orders with no email on file."""
    if not types:
        return []
    qs = ",".join("?" * len(types))
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT m.id, m.order_id, m.message_type, m.message_body,
                       o.customer_email, o.recipient_name
                FROM customer_messages m JOIN orders o ON o.order_id = m.order_id
                WHERE m.sent = 0 AND m.message_type IN ({qs})
                  AND o.customer_email LIKE '%@%'
                ORDER BY m.created_at""",
            tuple(types),
        ).fetchall()
        return [dict(r) for r in rows]


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
                 updated_at=datetime('now')
                 WHERE accepted=0""",   # an ACCEPTED design is immutable: the
            # customer's approved personalization can't be silently overwritten by
            # a later /design or /confirm for the same (email, design_id).
            (email, design_id, order_id, design_json, summary))
        return cur.lastrowid or 0


# ── Official product images (#181) ──────────────────────────────

def upsert_product_image(gelato_sku: str, image_url: str, *,
                         gelato_product_uid: str = "", etsy_listing_id: str = "",
                         etsy_image_id: str = "", image_rank: int = 0,
                         image_type: str = "mockup",
                         source: str = "gelato_ecommerce") -> int:
    """Insert or refresh one product<->official-image row. Idempotent on
    (gelato_sku, gelato_product_uid, image_rank): a daily re-sync updates the URL +
    stamps last_seen_at rather than inserting a duplicate. Returns 0 if no sku/url."""
    gelato_sku = (gelato_sku or "").strip()
    image_url = (image_url or "").strip()
    if not gelato_sku or not image_url:
        return 0
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO gelato_product_images
                 (gelato_sku, gelato_product_uid, etsy_listing_id, etsy_image_id,
                  image_url, image_rank, image_type, source, is_active, last_seen_at)
               VALUES (?,?,?,?,?,?,?,?, 1, datetime('now'))
               ON CONFLICT(gelato_sku, gelato_product_uid, image_rank) DO UPDATE SET
                 image_url=excluded.image_url,
                 etsy_listing_id=COALESCE(NULLIF(excluded.etsy_listing_id,''), etsy_listing_id),
                 etsy_image_id=COALESCE(NULLIF(excluded.etsy_image_id,''), etsy_image_id),
                 image_type=excluded.image_type, source=excluded.source,
                 is_active=1, last_seen_at=datetime('now')""",
            (gelato_sku, (gelato_product_uid or ""), (etsy_listing_id or ""),
             (etsy_image_id or ""), image_url, int(image_rank), image_type, source))
        return cur.lastrowid or 0


def get_product_images(gelato_sku: str = "", active_only: bool = True) -> list[dict]:
    """Official images for one SKU (or all), ranked. Empty when none."""
    q, args = "SELECT * FROM gelato_product_images WHERE 1=1", []
    if gelato_sku:
        q += " AND gelato_sku=?"
        args.append(gelato_sku.strip())
    if active_only:
        q += " AND is_active=1"
    q += " ORDER BY gelato_sku, image_rank"
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, args)]


def deactivate_stale_product_images(seen_stamp: str) -> int:
    """Flag is_active=0 for rows NOT refreshed this run (last_seen_at < seen_stamp) -
    so an image retired from the store is retired here too. Returns the count."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE gelato_product_images SET is_active=0 "
            "WHERE is_active=1 AND last_seen_at < ?", (seen_stamp,))
        return cur.rowcount


def deactivate_product_images(gelato_sku: str) -> int:
    """MANUAL OVERRIDE (#182-P1): pull ALL official images for one SKU (is_active=0)
    right now — the owner's escape hatch when a synced image is wrong (e.g. depicts the
    wrong product/variant) and shouldn't wait for the daily stale-sweep. The storefront
    then falls back to the tier-variant photo. Returns the number of rows deactivated."""
    gelato_sku = (gelato_sku or "").strip()
    if not gelato_sku:
        return 0
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE gelato_product_images SET is_active=0 "
            "WHERE gelato_sku=? AND is_active=1", (gelato_sku,))
        return cur.rowcount


# ── Uptime heartbeat (#182) ─────────────────────────────────────

def record_sync_run(job: str, ok: bool = True, detail: str = "") -> None:
    """Stamp that a daily automation `job` just ran (ok or not). The uptime signal:
    a job that stops running leaves no fresh row -> the recency check alerts."""
    job = (job or "").strip()
    if not job:
        return
    # Best-effort by construction: a monitoring write must NEVER take down the
    # monitored job. On a locked/read-only/corrupt DB _conn() can raise, so swallow
    # it here (the recency check then sees a stale row and alerts, as intended).
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO sync_runs (job, ok, detail) VALUES (?,?,?)",
                (job, 1 if ok else 0, (detail or "")[:500]))
    except Exception as exc:  # noqa: BLE001 - uptime stamp must not break the job
        logger.debug("record_sync_run skipped for %s: %s", job, exc)


def last_sync_run(job: str) -> dict:
    """The most recent run of `job` as {ran_at, ok, detail}, or {} if it never ran."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT ran_at, ok, detail FROM sync_runs WHERE job=? "
            "ORDER BY id DESC LIMIT 1", ((job or "").strip(),)).fetchone()
        return dict(row) if row else {}


# ── Audit trail (#182-P2) ───────────────────────────────────────

def record_security_event(event: str, detail: str = "", actor: str = "system") -> None:
    """Append one SENSITIVE/privileged action to the audit trail (an admin lock
    override, a manual image override, ...). Best-effort by construction: an audit
    write must never crash the action it records, but a failure IS logged at WARNING
    (not debug) because a missing security record matters more than a missing heartbeat."""
    event = (event or "").strip()
    if not event:
        return
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO security_events (event, actor, detail) VALUES (?,?,?)",
                (event, (actor or "system").strip() or "system", (detail or "")[:1000]))
    except Exception as exc:  # noqa: BLE001 - audit write must not break the action
        logger.warning("SECURITY audit write failed for %s: %s", event, exc)


def recent_security_events(limit: int = 50, event: str = "") -> list[dict]:
    """The most recent audit rows (optionally filtered to one `event`), newest first."""
    q = "SELECT at, event, actor, detail FROM security_events"
    args: list = []
    if event:
        q += " WHERE event=?"
        args.append(event.strip())
    q += " ORDER BY id DESC LIMIT ?"
    args.append(int(limit))
    with _conn() as conn:
        return [dict(r) for r in conn.execute(q, args)]


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


def link_design_to_order(email: str, order_id: str) -> int:
    """Attach the customer's most-recent UNLINKED saved design to an order, so the
    confirmed personalization (including any 12-month calendar photo URLs) travels
    with the order for production. Returns the linked design row id (0 if none)."""
    email = (email or "").strip().lower()
    if "@" not in email or not order_id:
        return 0
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, design_json FROM saved_designs WHERE email=? "
            "AND (order_id IS NULL OR order_id='') "
            "ORDER BY updated_at DESC", (email,)).fetchall()
        if not rows:
            return 0
        if len(rows) == 1:
            row = rows[0]                         # unambiguous - the common case
        else:
            # MULTIPLE unlinked designs: blindly taking the most recent (the old
            # behaviour) could attach the WRONG artwork to this order line, since the
            # Etsy line order and the save-recency order are unrelated. Match by the
            # order's product identity; link ONLY on an unambiguous single match -
            # otherwise link nothing (a missing design is recoverable; a wrong,
            # already-printed made-to-order item is not).
            row = _match_unlinked_design(order_id, rows)
            if row is None:
                return 0
        conn.execute(
            "UPDATE saved_designs SET order_id=?, updated_at=datetime('now') WHERE id=?",
            (order_id, row["id"]))
        design_json = row["design_json"]
    # Carry the design's print file onto the order so production has the artwork even
    # for a Pro Designer / calendar order (best-effort; never blocks the link).
    try:
        _propagate_design_artwork(order_id, design_json)
    except Exception as exc:  # noqa: BLE001 - never block the link, but never silent:
        # a failed propagation means production may lack the design's print file.
        logger.warning("_propagate_design_artwork failed for %s: %s", order_id, exc)
    return row["id"]


def _design_tokens(design_json: str) -> set:
    """Product-identity tokens (format/size/type) found in a saved design, top-level
    or in its first cart line - for correlating a design to an order line."""
    import json as _json
    try:
        d = _json.loads(design_json or "{}") or {}
    except (TypeError, ValueError):
        return set()
    src = dict(d)
    lines = ((d.get("cart") or {}).get("lines")) or []
    if lines and isinstance(lines[0], dict):
        src.update({k: v for k, v in lines[0].items() if k not in src})
    toks = {str(src.get(k) or "").strip().lower()
            for k in ("product_type", "fmt", "format", "material", "size")}
    toks.discard("")
    return toks


def _match_unlinked_design(order_id: str, rows: list):
    """Pick the saved design whose product identity matches the order, or None when
    the match is ambiguous (0 or 2+ candidates) - never guess on a print."""
    o = get_order(order_id) or {}
    o_toks = {str(o.get(k) or "").strip().lower()
              for k in ("product_type", "material", "size")}
    o_toks.discard("")
    if not o_toks:
        return None
    matches = [r for r in rows if o_toks & _design_tokens(r["design_json"])]
    return matches[0] if len(matches) == 1 else None


def _propagate_design_artwork(order_id: str, design_json: str) -> None:
    """If a linked design carries a hosted print URL (Pro Designer printUrl, or the
    first 12-month calendar photo), set it as the order's artwork_url - but only when
    the order doesn't already have one (don't clobber a real upload)."""
    import json as _json
    d = _json.loads(design_json or "{}")
    url = (d.get("printUrl") or "").strip()
    if not url:
        urls = ((d.get("cal") or {}).get("urls")) or []
        url = (urls[0] if urls else "") or ""
    if not url:
        return
    cur = get_order(order_id)
    if cur and not (cur.get("artwork_url") or "").strip():
        update_order(order_id, artwork_url=url)


def get_design_for_order(order_id: str) -> dict | None:
    """Return the saved design linked to an order (most recent), or None. Lets
    fulfillment retrieve the full personalization - e.g. all 12 calendar months."""
    if not order_id:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM saved_designs WHERE order_id=? ORDER BY updated_at DESC LIMIT 1",
            (order_id,)).fetchone()
        return dict(row) if row else None


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

EVENT_RETENTION_DAYS = 365


def prune_event_tables(days: int = EVENT_RETENTION_DAYS) -> dict:
    """Retention prune for the append-only heartbeat + audit tables (sync_runs,
    security_events): delete rows older than `days`. Both grow slowly, so a 1-year
    window keeps them tiny without losing recent history (security_events is a security
    audit trail, hence the generous default). The cutoff uses datetime('now', ...) (UTC),
    matching how the columns are written. Never raises; returns {table: deleted_count}.
    Table/column names are hardcoded literals (no injection); the cutoff is parameterized.
    """
    out: dict = {}
    if not DB_PATH.exists():
        return out
    cutoff = f"-{int(days)} days"
    try:
        with _conn() as conn:
            for table, col in (("sync_runs", "ran_at"), ("security_events", "at")):
                try:
                    cur = conn.execute(
                        f"DELETE FROM {table} WHERE {col} < datetime('now', ?)", (cutoff,))
                    out[table] = cur.rowcount
                except sqlite3.OperationalError:
                    out[table] = 0          # table absent on a very old DB - skip
    except Exception as exc:  # noqa: BLE001 - hygiene must never break maintenance
        logger.debug("prune_event_tables skipped: %s", exc)
    return out


def db_maintenance() -> dict:
    """Run database health + performance maintenance.

    - integrity_check : detects corruption early
    - retention prune : trims the sync_runs / security_events history (1-year window)
    - wal_checkpoint  : flushes the write-ahead log back into the main file
    - VACUUM          : reclaims space and defragments for faster queries
    Returns metrics (size before/after, integrity result, pruned counts). Safe daily.
    """
    if not DB_PATH.exists():
        return {"ran": False, "reason": "no database yet"}
    size_before = DB_PATH.stat().st_size
    pruned = prune_event_tables()            # trim heartbeat/audit history before VACUUM
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
        "pruned": pruned,                            # {sync_runs, security_events} rows deleted
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
                # hold_validation is a money-gate failure that previously had no
                # owner-facing surfacing; hold_photo waits on a re-upload; on_hold is
                # a vendor-side production pause (Gelato) that needs a human chase;
                # submit_unconfirmed is an ambiguous send (vendor MAY have charged +
                # started producing) that is intentionally never auto-retried, so it
                # MUST be surfaced for manual reconciliation or it sits invisible.
                # approved_ready_to_print is a manual-flow order awaiting the owner's
                # upload to the print partner - it had no follow-up surfacing.
                "WHERE status IN ('proof_sent','error','hold_validation','hold_photo',"
                "'on_hold','submit_unconfirmed','approved_ready_to_print') "
                "ORDER BY created_at"
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
