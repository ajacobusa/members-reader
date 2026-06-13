"""Financial reporting expansion: fee-type breakdown (which fees reduce profit -
especially Offsite Ads), refund/cancellation rates, and traffic-source report.

Fee amounts come from the Etsy Finances statement CSV (etsy_finance_import.
import_statement_csv); refund/cancellation rates and traffic source come from
the orders table. All real data - never estimated.
"""
from __future__ import annotations

_FEE_LABEL = {
    "listing": "Listing fee", "transaction": "Transaction fee",
    "processing": "Payment processing", "offsite_ads": "Offsite Ads",
    "refunds": "Refunds", "other_fees": "Other fees",
}

# acquisition_source (raw) -> friendly Etsy traffic bucket.
_SOURCE_LABEL = {
    "offsite_ads": "Offsite Ads", "offsite ads": "Offsite Ads", "ads": "Offsite Ads",
    "etsy_search": "Etsy Search", "search": "Etsy Search", "etsy search": "Etsy Search",
    "etsy_app": "Etsy App", "app": "Etsy App",
    "direct": "Direct", "direct_traffic": "Direct", "": "Unknown",
}


def fee_breakdown(summary: dict, revenue: float) -> dict:
    """Each fee type as $ and % of revenue (highest first) + total. `summary`
    is import_statement_csv's output; `revenue` the period's gross sales."""
    rows = []
    for key, amount in summary.items():
        amount = round(float(amount or 0), 2)
        if amount <= 0:
            continue
        rows.append({
            "fee": key, "label": _FEE_LABEL.get(key, key),
            "amount": amount,
            "pct_of_revenue": round(amount / revenue * 100, 2) if revenue else 0.0,
        })
    rows.sort(key=lambda r: r["amount"], reverse=True)
    total = round(sum(r["amount"] for r in rows), 2)
    return {"rows": rows, "total_fees": total, "revenue": round(revenue, 2),
            "total_pct_of_revenue": round(total / revenue * 100, 2) if revenue else 0.0}


def refund_cancellation_rates(orders: list[dict]) -> dict:
    """Refund-rate and cancellation-rate across all orders (these directly hit
    profitability and Etsy standing)."""
    n = len(orders)
    refunded = sum(1 for o in orders if (o.get("status") or "") == "refunded")
    cancelled = sum(1 for o in orders if (o.get("status") or "") == "cancelled")
    return {
        "orders": n,
        "refunded": refunded, "cancelled": cancelled,
        "refund_rate_pct": round(refunded / n * 100, 1) if n else 0.0,
        "cancellation_rate_pct": round(cancelled / n * 100, 1) if n else 0.0,
    }


def traffic_source_report(orders: list[dict]) -> list[dict]:
    """Orders + revenue grouped by traffic source (Offsite Ads / Etsy Search /
    Etsy App / Direct), so you see where sales originate."""
    agg: dict = {}
    for o in orders:
        if (o.get("status") or "") in ("cancelled", "error"):
            continue
        raw = (o.get("acquisition_source") or "").strip().lower()
        label = _SOURCE_LABEL.get(raw, "Unknown")
        row = agg.setdefault(label, {"source": label, "orders": 0, "revenue": 0.0})
        row["orders"] += 1
        row["revenue"] = round(row["revenue"] + float(o.get("sale_price") or 0), 2)
    return sorted(agg.values(), key=lambda r: r["revenue"], reverse=True)


def format_financial_report(orders: list[dict], fee_summary: dict = None) -> str:
    """Combined financial report: fee breakdown (if a statement was imported),
    refund/cancellation rates, and traffic source."""
    revenue = round(sum(float(o.get("sale_price") or 0) for o in orders
                        if (o.get("status") or "") not in ("cancelled", "error")), 2)
    lines = ["=" * 60, "FINANCIAL REPORT", "=" * 60,
             f"  Gross revenue: ${revenue:,.2f}"]
    if fee_summary:
        fb = fee_breakdown(fee_summary, revenue)
        lines.append(f"\nFEES (which reduce profit) - ${fb['total_fees']:,.2f} "
                     f"= {fb['total_pct_of_revenue']}% of revenue:")
        for r in fb["rows"]:
            lines.append(f"    {r['label']:<20} ${r['amount']:>8.2f}  "
                         f"({r['pct_of_revenue']}% of rev)")
    rc = refund_cancellation_rates(orders)
    lines.append(f"\nQUALITY: refund rate {rc['refund_rate_pct']}% "
                 f"({rc['refunded']}), cancellation rate "
                 f"{rc['cancellation_rate_pct']}% ({rc['cancelled']}) of "
                 f"{rc['orders']} orders")
    lines.append("\nTRAFFIC SOURCE (where sales originate):")
    for r in traffic_source_report(orders):
        lines.append(f"    {r['source']:<16} {r['orders']:>4} orders  "
                     f"${r['revenue']:>9.2f}")
    lines.append("=" * 60)
    return "\n".join(lines)
