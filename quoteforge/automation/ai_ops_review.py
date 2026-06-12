"""AI ops review - audit every step, flag issues, suggest improvements.

Collects deterministic signals across the whole pipeline (orders, holds,
approvals, margins, P&L, costs, catalog, backups, schedule) - this part is free
and always runs. Then Claude synthesizes a prioritized, proactive improvement
plan from those signals (with a rule-based fallback in TEST_MODE / no key).

Run: admin ai-review [email]   |   scheduled weekly.
"""
from __future__ import annotations


def collect_signals() -> dict:
    """Gather health + business signals from every subsystem. Never raises."""
    s: dict = {}

    def _try(key, fn):
        """Store fn() under `key`, capturing any exception as an error dict."""
        try:
            s[key] = fn()
        except Exception as exc:  # noqa: BLE001
            s[key] = {"error": str(exc)}

    def _orders_by_status():
        """Tally all orders grouped by their status field."""
        from quoteforge.db.database import init_db, get_all_orders
        init_db()
        from collections import Counter
        c = Counter((o.get("status") or "?") for o in get_all_orders(limit=100000))
        return dict(c)
    _try("orders_by_status", _orders_by_status)

    _try("pending_approvals", lambda: len(_imp("quoteforge.db.database",
         "get_pending_approvals")()))

    def _holds():
        """Count orders blocked by bad photos or preflight failures."""
        from quoteforge.db.database import get_all_orders
        held = [o for o in get_all_orders(limit=100000)
                if (o.get("status") or "") in ("needs_better_photo", "preflight_failed")]
        return len(held)
    _try("orders_on_hold", _holds)

    def _margins():
        """Count product variations whose margin is below the 60% floor."""
        from quoteforge.etsy.variations import build_variations
        vs = build_variations()
        below = [v for v in vs if v.margin_pct < 60]
        return {"variations": len(vs), "below_floor": len(below)}
    _try("margins", _margins)

    def _pnl():
        """Pull this month's P&L totals from the ledger."""
        from quoteforge.etsy.ledger import build_ledger
        t = build_ledger("month")["totals"]
        return {"revenue": t["revenue"], "net_profit": t["net_profit"],
                "margin_pct": t["margin_pct"], "orders": t["orders"]}
    _try("pnl_month", _pnl)

    def _catalog():
        """Summarize catalog size and vendor coverage."""
        from quoteforge.catalog.registry import list_products, VENDORS
        prods = list_products()
        vendors_used = {p["vendor"] for p in prods}
        return {"items": len(prods), "vendors_defined": len(VENDORS),
                "vendors_with_items": len(vendors_used)}
    _try("catalog", _catalog)

    def _backups():
        """Report database backup count and the most recent backup."""
        from quoteforge.db.database import list_backups
        bs = list_backups()
        return {"count": len(bs), "latest": (bs[0] if bs else None)}
    _try("backups", _backups)

    def _subs():
        """Count subscriptions expiring within the next 7 days."""
        from quoteforge.db.database import get_expiring_subscriptions
        return {"expiring_7d": len(get_expiring_subscriptions(7))}
    _try("subscriptions", _subs)

    return s


def _imp(mod, name):
    """Import `mod` lazily and return its attribute `name`."""
    import importlib
    return getattr(importlib.import_module(mod), name)


def _rule_findings(s: dict) -> list[str]:
    """Deterministic issue/opportunity flags from the signals (the fallback)."""
    f = []
    if isinstance(s.get("orders_on_hold"), int) and s["orders_on_hold"] > 0:
        f.append(f"ACTION: {s['orders_on_hold']} order(s) on hold (bad photo / "
                 "preflight) - resolve so they can print.")
    pa = s.get("pending_approvals")
    if isinstance(pa, int) and pa > 0:
        f.append(f"ACTION: {pa} item(s) await your approval (refunds/returns).")
    m = s.get("margins", {})
    if isinstance(m, dict) and m.get("below_floor"):
        f.append(f"RISK: {m['below_floor']} variation(s) below the 60% floor - "
                 "raise price or check Gelato cost.")
    b = s.get("backups", {})
    if isinstance(b, dict) and not b.get("count"):
        f.append("RISK: no database backups found - run backup-all.")
    c = s.get("catalog", {})
    if isinstance(c, dict) and c.get("vendors_with_items", 0) <= 1:
        f.append("GROWTH: only one vendor in use - add a 2nd POD/vendor or a "
                 "digital/service product to diversify.")
    sub = s.get("subscriptions", {})
    if isinstance(sub, dict) and sub.get("expiring_7d"):
        f.append(f"REVENUE: {sub['expiring_7d']} subscription(s) ending soon - "
                 "renewal reminders go out automatically; consider a win-back offer.")
    p = s.get("pnl_month", {})
    if isinstance(p, dict) and p.get("orders", 0) == 0:
        f.append("GROWTH: no sales recorded this month - drive traffic "
                 "(Pinterest, email, seasonal SEO) and confirm listings are live.")
    if not f:
        f.append("All clear: no blocking issues detected. Keep scaling listings "
                 "and watch conversion + margin.")
    return f


def ai_review(email: bool = False) -> dict:
    """Audit + (Claude) improvement plan. Returns the report dict."""
    import json
    s = collect_signals()
    findings = _rule_findings(s)
    from quoteforge.ai.assistant import ai_text
    fallback = "\n".join(f"- {x}" for x in findings)
    plan = ai_text(
        "You are an e-commerce operations advisor for a personalized wall-art "
        "print-on-demand shop (Etsy + Gelato). Given these JSON signals, list the "
        "TOP 5 prioritized, specific actions to fix issues and improve revenue/"
        "margin/efficiency. Be concrete and concise (one line each).\n\n"
        f"SIGNALS:\n{json.dumps(s, default=str)}\n\nDeterministic flags:\n{fallback}",
        operation="ai_ops_review", max_tokens=500, mock=fallback)
    report = {"signals": s, "findings": findings, "plan": plan}
    if email:
        try:
            from quoteforge.automation.emailer import _send_email
            from quoteforge.config import REPORT_RECIPIENT
            _send_email("Joffiels AI Ops Review", format_review_html(report),
                        to=REPORT_RECIPIENT)
            report["emailed"] = True
        except Exception:  # noqa: BLE001
            pass
    return report


def format_review_text(r: dict) -> str:
    """Render the review report as console-friendly plain text."""
    lines = ["=" * 60, "AI OPS REVIEW - issues & continuous improvement", "=" * 60,
             "\nIMPROVEMENT PLAN:", r["plan"], "\nDETERMINISTIC FLAGS:"]
    lines += [f"  - {x}" for x in r["findings"]]
    lines += ["\nSIGNALS:"]
    for k, v in r["signals"].items():
        lines.append(f"  {k}: {v}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_review_html(r: dict) -> str:
    """Wrap the plain-text review in minimal HTML for email delivery."""
    return ("<html><body style='font-family:Arial'><pre style='font-size:13px;"
            f"white-space:pre-wrap'>{format_review_text(r)}</pre></body></html>")
