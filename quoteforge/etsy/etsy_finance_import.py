"""Import ACTUAL Etsy financials from an Etsy CSV (Shop Manager -> Settings ->
Options -> Download Data -> Orders, or a Finances statement CSV).

Etsy is the marketplace facilitator - it collects payment, calculates/collects/
remits sales tax, and charges its own fees. The only way to get the REAL
per-order figures (order total, shipping collected, sales tax collected, Etsy
fees, net payout) is from Etsy's own data. This reads that CSV and writes the
real numbers onto matching orders, so reconciliation/financials stop estimating.

Column names vary across Etsy's CSV exports, so matching is tolerant (case- and
spacing-insensitive, with common aliases).
"""
from __future__ import annotations

from pathlib import Path

# Canonical field -> the header aliases Etsy uses across its CSV exports.
_ALIASES = {
    "order_id": ("order id", "order number", "receipt id"),
    "sale_price": ("order total", "total", "grand total"),
    "shipping_collected": ("order shipping", "shipping", "shipping paid"),
    "tax_collected": ("order sales tax", "sales tax", "tax"),
    "etsy_fees_actual": ("card processing fees", "fees", "transaction fees",
                         "etsy fees", "fees & taxes"),
    "net_payout": ("order net", "net", "net payout", "payout"),
}


def _money(s: str) -> float | None:
    """Parse a CSV money cell ('$52.21', '52.21', '') to a float, or None."""
    s = (s or "").strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _resolve_columns(headers: list[str]) -> dict:
    """Map canonical field -> actual header name present in this CSV."""
    norm = {h.strip().lower(): h for h in headers}
    out = {}
    for field, aliases in _ALIASES.items():
        for a in aliases:
            if a in norm:
                out[field] = norm[a]
                break
    return out


def import_orders_csv(path) -> dict:
    """Read an Etsy Orders/statement CSV and write the REAL financials onto each
    matching order (by etsy_order_id, else order_id). Returns {updated, rows,
    unmatched}."""
    import csv
    from quoteforge.db.database import (init_db, get_order_by_etsy_id,
                                        get_order, update_order)
    init_db()
    p = Path(path)
    if not p.exists():
        return {"updated": 0, "rows": 0, "unmatched": 0, "error": "file not found"}
    updated = unmatched = rows = 0
    with p.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = _resolve_columns(reader.fieldnames or [])
        oid_col = cols.get("order_id")
        for row in reader:
            rows += 1
            oid = (row.get(oid_col) or "").strip() if oid_col else ""
            if not oid:
                continue
            order = get_order_by_etsy_id(oid) or get_order(oid)
            if not order:
                unmatched += 1
                continue
            fields = {}
            for field in ("sale_price", "shipping_collected", "tax_collected",
                          "etsy_fees_actual", "net_payout"):
                col = cols.get(field)
                if col is not None:
                    val = _money(row.get(col))
                    if val is not None:
                        # Etsy reports fees as a charge; store the magnitude.
                        fields[field] = abs(val) if field == "etsy_fees_actual" else val
            if fields:
                update_order(order["order_id"], **fields)
                updated += 1
    return {"updated": updated, "rows": rows, "unmatched": unmatched}


def format_import_text(r: dict) -> str:
    """One-line summary of an Etsy finance import."""
    if r.get("error"):
        return f"Etsy import failed: {r['error']}"
    return (f"Etsy finance import: {r['updated']} order(s) updated with real "
            f"figures ({r['rows']} rows, {r['unmatched']} unmatched).")
