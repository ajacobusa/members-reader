"""Total Cost of Ownership calculator.

Breaks your real running cost into:
- FIXED monthly  (the software stack: AI, automation, renderer, listing renewals)
- VARIABLE       (Gelato print + Etsy fees — only on actual sales, self-funding)
- STARTUP        (one-time launch costs)

Pulls this month's real orders from the database for the variable side, and
your config for the fixed side, so the number tracks reality as you grow.
"""
from datetime import datetime

from quoteforge.config import (
    RENDERER, USE_MAKE_COM, MAKE_COM_COST, ANTHROPIC_COST_PER_ORDER,
    ETSY_LISTING_RENEWAL_PER_MONTH, DEFAULT_SALE_PRICE, DEFAULT_GELATO_COST,
)
from quoteforge.etsy.profit_calculator import RENDERER_COSTS, calculate_order_profit


def fixed_monthly_costs(listings: int, orders_per_month: int) -> dict:
    """The recurring monthly cost that does NOT depend on individual sales."""
    anthropic = round(max(1.0, orders_per_month * ANTHROPIC_COST_PER_ORDER), 2)
    make_com = MAKE_COM_COST if USE_MAKE_COM else 0.0
    renderer = RENDERER_COSTS.get(RENDERER, 0.0)
    renewals = round(listings * ETSY_LISTING_RENEWAL_PER_MONTH, 2)
    items = {
        "Anthropic (Claude Haiku)": anthropic,
        "Make.com automation": make_com,
        f"Renderer ({RENDERER})": renderer,
        "Etsy listing renewals": renewals,
        "Unsplash / Gmail / local PC": 0.0,
    }
    return {"items": items, "total": round(sum(items.values()), 2)}


def variable_monthly_costs(orders_per_month: int,
                           avg_sale_price: float, avg_gelato_cost: float) -> dict:
    """Per-sale costs paid out of revenue: Gelato print + Etsy fees + the real
    operating costs (packaging, reprint reserve, marketing) so the TCO net is
    fully loaded, not just contribution."""
    from quoteforge.etsy.profit_calculator import operating_order_profit
    p = calculate_order_profit(avg_sale_price, avg_gelato_cost)
    op = operating_order_profit(avg_sale_price, avg_gelato_cost)
    gelato = round(avg_gelato_cost * orders_per_month, 2)
    etsy = round(p["total_fees"] * orders_per_month, 2)
    packaging = round(op["packaging_cost"] * orders_per_month, 2)
    reserve = round(op["reprint_reserve"] * orders_per_month, 2)
    cac = round(op["cac"] * orders_per_month, 2)
    return {
        "gelato_print": gelato,
        "etsy_fees": etsy,
        "packaging": packaging,
        "reprint_reserve": reserve,
        "marketing_cac": cac,
        "total": round(gelato + etsy + packaging + reserve + cac, 2),
        "per_order_fees": p["total_fees"],
    }


def startup_costs(listings: int) -> dict:
    """One-time startup cost items and their total for a listing count."""
    items = {
        "Etsy listing fees ($0.20 each)": round(listings * 0.20, 2),
        "Sample print (1 poster + ship)": 13.0,
        "Software / shop setup / domain": 0.0,
    }
    return {"items": items, "total": round(sum(items.values()), 2)}


def estimate_tco(listings: int = 100, orders_per_month: int = 60,
                 avg_sale_price: float = DEFAULT_SALE_PRICE,
                 avg_gelato_cost: float = DEFAULT_GELATO_COST) -> dict:
    """Full TCO breakdown for the given listing count and order volume."""
    fixed = fixed_monthly_costs(listings, orders_per_month)
    variable = variable_monthly_costs(orders_per_month, avg_sale_price, avg_gelato_cost)
    startup = startup_costs(listings)

    revenue = round(orders_per_month * avg_sale_price, 2)
    total_monthly_cost = round(fixed["total"] + variable["total"], 2)
    net_profit = round(revenue - total_monthly_cost, 2)
    cost_pct = round((total_monthly_cost / revenue) * 100, 1) if revenue else 0.0
    fixed_pct = round((fixed["total"] / revenue) * 100, 1) if revenue else 0.0

    return {
        "inputs": {"listings": listings, "orders_per_month": orders_per_month,
                   "avg_sale_price": avg_sale_price, "avg_gelato_cost": avg_gelato_cost},
        "startup": startup,
        "fixed_monthly": fixed,
        "variable_monthly": variable,
        "revenue_monthly": revenue,
        "total_monthly_cost": total_monthly_cost,
        "fixed_cost_pct_of_revenue": fixed_pct,
        "total_cost_pct_of_revenue": cost_pct,
        "net_profit_monthly": net_profit,
        "net_profit_yearly": round(net_profit * 12, 2),
    }


def live_tco(listings: int = 100) -> dict:
    """TCO using THIS MONTH's real orders for volume + economics."""
    from quoteforge.etsy.financials import month_financials
    now = datetime.now()
    fin = month_financials(now.year, now.month)
    orders = fin["order_count"]
    avg_price = round(fin["revenue"] / orders, 2) if orders else DEFAULT_SALE_PRICE
    avg_gelato = round(fin["gelato_cost"] / orders, 2) if orders else DEFAULT_GELATO_COST
    tco = estimate_tco(listings, orders, avg_price, avg_gelato)
    tco["source"] = f"live ({orders} real orders this month)" if orders \
        else "projection (no real orders yet — using defaults)"
    return tco


def format_tco_text(tco: dict) -> str:
    """Render the TCO breakdown as printable console text."""
    i = tco["inputs"]
    lines = ["=" * 56, "QUOTEFORGE TOTAL COST OF OWNERSHIP", "=" * 56,
             f"Assumptions: {i['listings']} listings, {i['orders_per_month']} orders/mo, "
             f"${i['avg_sale_price']:.2f} avg sale, ${i['avg_gelato_cost']:.2f} avg print"]
    if "source" in tco:
        lines.append(f"Source: {tco['source']}")

    lines.append("\nONE-TIME STARTUP:")
    for k, v in tco["startup"]["items"].items():
        lines.append(f"  {k:38} ${v:>8.2f}")
    lines.append(f"  {'TOTAL STARTUP':38} ${tco['startup']['total']:>8.2f}")

    lines.append("\nFIXED MONTHLY (independent of sales):")
    for k, v in tco["fixed_monthly"]["items"].items():
        lines.append(f"  {k:38} ${v:>8.2f}")
    lines.append(f"  {'TOTAL FIXED / MONTH':38} ${tco['fixed_monthly']['total']:>8.2f}")

    lines.append("\nVARIABLE MONTHLY (paid from each sale):")
    v = tco["variable_monthly"]
    lines.append(f"  {'Gelato printing':38} ${v['gelato_print']:>8.2f}")
    lines.append(f"  {'Etsy fees':38} ${v['etsy_fees']:>8.2f}")
    lines.append(f"  {'Packaging':38} ${v.get('packaging', 0):>8.2f}")
    lines.append(f"  {'Reprint/breakage reserve':38} ${v.get('reprint_reserve', 0):>8.2f}")
    if v.get("marketing_cac", 0):
        lines.append(f"  {'Marketing (CAC)':38} ${v['marketing_cac']:>8.2f}")
    lines.append(f"  {'TOTAL VARIABLE / MONTH':38} ${v['total']:>8.2f}")

    lines.append("\nBOTTOM LINE (per month):")
    lines.append(f"  {'Revenue':38} ${tco['revenue_monthly']:>8.2f}")
    lines.append(f"  {'Total cost (fixed+variable)':38} ${tco['total_monthly_cost']:>8.2f}")
    lines.append(f"  {'NET PROFIT':38} ${tco['net_profit_monthly']:>8.2f}")
    lines.append(f"  {'Fixed cost as % of revenue':38} {tco['fixed_cost_pct_of_revenue']:>7.1f}%")
    lines.append(f"  {'Net profit / YEAR':38} ${tco['net_profit_yearly']:>8.2f}")
    lines.append("=" * 56)
    return "\n".join(lines)
