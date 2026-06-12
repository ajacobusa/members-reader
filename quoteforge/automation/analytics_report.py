"""Analytics block for the daily report: Etsy shop stats, Google Analytics,
Microsoft Clarity.

Honest by design - it shows REAL numbers where an API exists and clear status +
dashboard links where it doesn't:
  * Etsy: visit/views stats have no seller API, so we report our own confirmed
    orders + revenue (from the DB) and link to the Etsy Stats dashboard.
  * Google Analytics: pulls users/sessions via the GA4 Data API IF
    GA_PROPERTY_ID + GA_SERVICE_ACCOUNT_FILE are set and the lib is installed;
    otherwise shows 'active (G-XXXX)' + a dashboard link.
  * Microsoft Clarity: pulls live insights via the Data Export API IF
    CLARITY_API_TOKEN is set; otherwise status + dashboard link.
Never fabricates metrics.
"""
from __future__ import annotations


def _etsy_block() -> dict:
    """Today and month-to-date Etsy orders/revenue from our own ledger."""
    from quoteforge.etsy.ledger import build_ledger
    t = build_ledger("today")["totals"]
    mtd = build_ledger("month")["totals"]
    return {"orders_today": t.get("orders", 0),
            "revenue_today": t.get("revenue", 0),
            "orders_mtd": mtd.get("orders", 0),
            "revenue_mtd": mtd.get("revenue", 0),
            "dashboard": "https://www.etsy.com/your/shops/me/stats"}


def _ga_block() -> dict:
    """Google Analytics status plus GA4 metrics when API access is configured."""
    import os
    from quoteforge.config import GA_MEASUREMENT_ID
    out = {"configured": bool(GA_MEASUREMENT_ID), "id": GA_MEASUREMENT_ID,
           "dashboard": "https://analytics.google.com/", "metrics": None}
    prop = os.getenv("GA_PROPERTY_ID", "").strip()
    svc = os.getenv("GA_SERVICE_ACCOUNT_FILE", "").strip()
    if not (prop and svc):
        return out
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Metric, RunReportRequest)
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(svc)
        client = BetaAnalyticsDataClient(credentials=creds)
        req = RunReportRequest(
            property=f"properties/{prop}",
            date_ranges=[DateRange(start_date="1daysAgo", end_date="today")],
            metrics=[Metric(name="activeUsers"), Metric(name="sessions"),
                     Metric(name="conversions")])
        resp = client.run_report(req)
        row = resp.rows[0].metric_values if resp.rows else []
        if row:
            out["metrics"] = {"users": row[0].value, "sessions": row[1].value,
                              "conversions": row[2].value}
    except Exception as exc:  # noqa: BLE001
        out["note"] = f"GA API unavailable ({type(exc).__name__})"
    return out


def _clarity_block() -> dict:
    """Microsoft Clarity status plus live insights when an API token is set."""
    import os
    from quoteforge.config import CLARITY_PROJECT_ID
    out = {"configured": bool(CLARITY_PROJECT_ID),
           "dashboard": "https://clarity.microsoft.com/", "metrics": None}
    token = os.getenv("CLARITY_API_TOKEN", "").strip()
    if not token:
        return out
    try:
        import requests
        r = requests.get(
            "https://www.clarity.ms/export-data/api/v1/project-live-insights",
            headers={"Authorization": f"Bearer {token}"},
            params={"numOfDays": 1}, timeout=20)
        if r.status_code == 200:
            out["metrics"] = r.json()
        else:
            out["note"] = f"Clarity API HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        out["note"] = f"Clarity API unavailable ({type(exc).__name__})"
    return out


def analytics_summary() -> dict:
    """Collect Etsy, GA, and Clarity blocks; each is best-effort."""
    def _s(fn):
        """Run fn(), returning an error dict instead of raising."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
    return {"etsy": _s(_etsy_block), "ga": _s(_ga_block),
            "clarity": _s(_clarity_block)}


def format_analytics_text(a: dict) -> str:
    """Render the analytics summary as indented plain-text report lines."""
    e = a.get("etsy", {})
    ga = a.get("ga", {})
    cl = a.get("clarity", {})
    lines = ["ANALYTICS:"]
    lines.append(f"  Etsy (orders/rev)  : today {e.get('orders_today', 0)} / "
                 f"${e.get('revenue_today', 0)}  |  MTD {e.get('orders_mtd', 0)} / "
                 f"${e.get('revenue_mtd', 0)}")
    lines.append(f"     Etsy Stats -> {e.get('dashboard', '')}")
    if ga.get("metrics"):
        m = ga["metrics"]
        lines.append(f"  Google Analytics   : users {m['users']}, sessions "
                     f"{m['sessions']}, conversions {m['conversions']}")
    elif ga.get("configured"):
        lines.append(f"  Google Analytics   : active ({ga.get('id')}) - "
                     f"{ga.get('note', 'view dashboard')} -> {ga.get('dashboard')}")
    else:
        lines.append("  Google Analytics   : not set (add GA_MEASUREMENT_ID)")
    if cl.get("metrics"):
        lines.append(f"  Microsoft Clarity  : {cl['metrics']}")
    elif cl.get("configured"):
        lines.append(f"  Microsoft Clarity  : active - "
                     f"{cl.get('note', 'view dashboard')} -> {cl.get('dashboard')}")
    else:
        lines.append("  Microsoft Clarity  : not set (add CLARITY_PROJECT_ID)")
    return "\n".join(lines)
