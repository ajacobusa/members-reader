"""Profit and scaling calculator for the Etsy + Gelato business."""

ETSY_TRANSACTION_FEE = 0.065   # 6.5%
ETSY_LISTING_FEE = 0.20        # per listing
ETSY_PAYMENT_FEE = 0.03        # 3% payment processing
ETSY_LISTING_RENEWAL = 0.20    # every 4 months per listing


def calculate_order_profit(
    sale_price: float,
    gelato_cost: float,
    shipping_collected: float = 0.0,
    shipping_cost: float = 0.0,
) -> dict:
    """Calculate net profit for a single Etsy order."""
    etsy_transaction = round(sale_price * ETSY_TRANSACTION_FEE, 2)
    etsy_payment = round(sale_price * ETSY_PAYMENT_FEE, 2)
    total_fees = round(etsy_transaction + etsy_payment + ETSY_LISTING_FEE, 2)
    net_profit = round(sale_price + shipping_collected - gelato_cost - shipping_cost - total_fees, 2)
    margin_pct = round((net_profit / sale_price) * 100, 1) if sale_price > 0 else 0.0
    return {
        "sale_price": sale_price,
        "gelato_cost": gelato_cost,
        "etsy_transaction_fee": etsy_transaction,
        "etsy_payment_fee": etsy_payment,
        "etsy_listing_fee": ETSY_LISTING_FEE,
        "total_fees": total_fees,
        "net_profit": net_profit,
        "margin_pct": margin_pct,
    }


def monthly_revenue_forecast(
    avg_daily_sales: float,
    avg_order_value: float,
    avg_gelato_cost: float,
    active_listings: int,
    monthly_ad_spend: float = 0.0,
) -> dict:
    """Forecast monthly revenue, costs, and profit."""
    monthly_orders = round(avg_daily_sales * 30, 1)
    gross_revenue = round(monthly_orders * avg_order_value, 2)
    total_gelato_cost = round(monthly_orders * avg_gelato_cost, 2)
    etsy_fees = round(
        gross_revenue * (ETSY_TRANSACTION_FEE + ETSY_PAYMENT_FEE)
        + monthly_orders * ETSY_LISTING_FEE,
        2,
    )
    listing_renewals = round((active_listings / 4) * ETSY_LISTING_RENEWAL, 2)
    net_profit = round(
        gross_revenue - total_gelato_cost - etsy_fees - listing_renewals - monthly_ad_spend,
        2,
    )
    roi_pct = round(
        (net_profit / (total_gelato_cost + etsy_fees + monthly_ad_spend + 0.01)) * 100,
        1,
    )
    return {
        "monthly_orders": monthly_orders,
        "gross_revenue": gross_revenue,
        "gelato_costs": total_gelato_cost,
        "etsy_fees": etsy_fees,
        "listing_renewals": listing_renewals,
        "ad_spend": monthly_ad_spend,
        "net_profit": net_profit,
        "roi_pct": roi_pct,
        "break_even_orders": _break_even(avg_order_value, avg_gelato_cost),
    }


def _break_even(avg_price: float, avg_cost: float) -> float:
    """Orders per month needed to break even on fixed costs."""
    profit_per_order = (
        avg_price * (1 - ETSY_TRANSACTION_FEE - ETSY_PAYMENT_FEE)
        - avg_cost
        - ETSY_LISTING_FEE
    )
    return round(100 / profit_per_order, 1) if profit_per_order > 0 else 999.0


def scaling_milestones() -> list[dict]:
    """Return the 6 scaling milestones from 0 to $20k/month."""
    return [
        {
            "milestone": "Phase 1 — Validate",
            "listings": 30,
            "daily_sales": 0.5,
            "monthly_revenue": 450,
            "monthly_profit": 280,
            "focus": "Manual. Test 7 niches. Get first 10 sales.",
        },
        {
            "milestone": "Phase 2 — Build",
            "listings": 100,
            "daily_sales": 2,
            "monthly_revenue": 1800,
            "monthly_profit": 1100,
            "focus": "Expand to 100 listings. Add canvas + framed.",
        },
        {
            "milestone": "Phase 3 — Automate",
            "listings": 300,
            "daily_sales": 6,
            "monthly_revenue": 5400,
            "monthly_profit": 3200,
            "focus": "Automate quotes via QuoteForge. Hire 1 VA.",
        },
        {
            "milestone": "Phase 4 — Scale",
            "listings": 600,
            "daily_sales": 14,
            "monthly_revenue": 12600,
            "monthly_profit": 7500,
            "focus": "Pinterest + Etsy ads. 2 VAs. SEO strategy.",
        },
        {
            "milestone": "Phase 5 — Dominate",
            "listings": 1000,
            "daily_sales": 25,
            "monthly_revenue": 22500,
            "monthly_profit": 13500,
            "focus": "1,000 listings. Shopify store. Wholesale.",
        },
        {
            "milestone": "Phase 6 — Business",
            "listings": 2000,
            "daily_sales": 50,
            "monthly_revenue": 45000,
            "monthly_profit": 27000,
            "focus": "Full team. Multiple shops. B2B corporate sales.",
        },
    ]


def canva_template_roi(
    templates_created: int,
    avg_designs_per_template: int = 20,
) -> dict:
    """ROI from investing time in Canva templates."""
    total_listings = templates_created * avg_designs_per_template
    time_per_template_hrs = 1.5
    total_time_hrs = templates_created * time_per_template_hrs
    # assume 80% sell at least once/month at $28 avg
    potential_monthly_revenue = total_listings * 0.8 * 28
    return {
        "templates": templates_created,
        "total_listings": total_listings,
        "time_invested_hrs": total_time_hrs,
        "potential_monthly_revenue": round(potential_monthly_revenue, 2),
        "revenue_per_hr_invested": round(potential_monthly_revenue / total_time_hrs, 2),
    }
