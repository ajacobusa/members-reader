# QuoteForge - Power BI Data Model & Report Spec

## How the model fits together (star schema)

**Fact tables**
- `fact_orders` - one row per order (the grain). Foreign keys: `order_date`,
  `vendor`, `channel`, `product_type`.
- `fact_ledger_daily` - one row per day (revenue, COGS, fees, opex, net profit).
- `fact_fees` - fee type x amount x % of revenue (incl. Offsite Ads).
- `fact_traffic` - orders & revenue by traffic source.

**Dimension tables**
- `dim_date` (mark as the date table; key = `date`)
- `dim_vendor` (`vendor`), `dim_channel` (`channel`), `dim_product` (`product_type`)

**Relationships (all single-direction, 1 -> *)**
- `dim_date[date]`     1 -> *  `fact_orders[order_date]`
- `dim_date[date]`     1 -> *  `fact_ledger_daily[date]`
- `dim_vendor[vendor]` 1 -> *  `fact_orders[vendor]`
- `dim_channel[channel]` 1 -> * `fact_orders[channel]`
- `dim_product[product_type]` 1 -> * `fact_orders[product_type]`

## Report pages to build (the "charts")

**Page 1 - Executive Overview**
- KPI cards: Revenue, Net Profit, Net Margin %, Orders, AOV
- Line chart: Revenue & Net Profit by `dim_date[date]`
- Donut: Cost mix (COGS / Etsy Fees / API / OpEx from `fact_ledger_daily`)

**Page 2 - Financial Detail**
- Bar: `fact_fees[label]` by [Total Fees] (Offsite Ads highlighted)
- Cards: Offsite Ads % of Revenue, Refund Rate %, Cancellation Rate %
- Table: fee type, amount, % of revenue

**Page 3 - Sales & Operations**
- Bar: Net Profit by `dim_vendor`, by `dim_channel`, by `dim_product`
- Pie: Revenue by `fact_traffic[source]`
- Funnel: order count by `fact_orders[status]`

**Page 4 - Customers**
- Cards: Repeat Rate %, Avg CLV, Lapsed customers
  (load `Excel/03_Customer_Analytics.xlsx` or extend the model with a
  `fact_customers` export if you want these native in Power BI)
