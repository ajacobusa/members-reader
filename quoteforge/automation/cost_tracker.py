"""API cost capture + daily reporting.

Records the real cost of every metered API call (primarily Anthropic/Claude
token usage) into the api_costs table, then aggregates it for a detailed daily
report. Gives you exact visibility into what the automation is spending.

Anthropic pricing is per 1M tokens (USD), input/output separately.
"""
from datetime import datetime, timedelta

# USD per 1,000,000 tokens (input, output). Keep in sync with current pricing.
ANTHROPIC_PRICING = {
    "claude-haiku-4-5":  (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8":   (5.00, 25.00),
}
_DEFAULT_PRICE = (1.00, 5.00)  # assume Haiku if model unknown


def anthropic_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a Claude call from token counts."""
    in_rate, out_rate = ANTHROPIC_PRICING.get(model, _DEFAULT_PRICE)
    return round(input_tokens / 1_000_000 * in_rate
                 + output_tokens / 1_000_000 * out_rate, 6)


def record_anthropic_usage(model: str, usage, operation: str = "generation",
                           order_id: str = "") -> float:
    """Record a Claude call's cost from its response.usage object. Best-effort."""
    try:
        in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage, "output_tokens", 0) or 0)
        cost = anthropic_cost(model, in_tok, out_tok)
        from quoteforge.db.database import record_api_cost
        record_api_cost("anthropic", cost, model=model, operation=operation,
                        input_tokens=in_tok, output_tokens=out_tok,
                        order_id=order_id)
        return cost
    except Exception:  # noqa: BLE001 - never let cost logging break generation
        return 0.0


def record_flat_cost(provider: str, cost_usd: float, operation: str = "",
                     units: int = 1, order_id: str = "") -> None:
    """Record a non-token cost (e.g. an image generation or a Gelato charge)."""
    try:
        from quoteforge.db.database import record_api_cost
        record_api_cost(provider, cost_usd, operation=operation, units=units,
                        order_id=order_id)
    except Exception:  # noqa: BLE001
        pass


# ── Reporting ────────────────────────────────────────────────────

def _day_bounds(day: datetime) -> tuple[str, str]:
    """Start/end timestamp strings covering the calendar day of `day`."""
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return (start.strftime("%Y-%m-%d %H:%M:%S"),
            (start + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"))


def cost_report(period: str = "today") -> dict:
    """Aggregate API costs for 'today', 'week', or 'month'."""
    from quoteforge.db.database import init_db, get_api_costs
    init_db()
    now = datetime.now()
    if period == "today":
        since, until = _day_bounds(now)
    elif period == "week":
        since = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        until = ""
    elif period == "month":
        since = now.replace(day=1, hour=0, minute=0, second=0,
                            microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        until = ""
    else:
        since, until = "", ""

    rows = get_api_costs(since, until)
    by_provider: dict[str, dict] = {}
    by_operation: dict[str, dict] = {}
    total_cost = total_in = total_out = 0
    for r in rows:
        total_cost += r["cost_usd"]
        total_in += r["input_tokens"]
        total_out += r["output_tokens"]
        p = by_provider.setdefault(r["provider"], {"calls": 0, "cost": 0.0})
        p["calls"] += 1; p["cost"] = round(p["cost"] + r["cost_usd"], 6)
        o = by_operation.setdefault(r["operation"] or "(unspecified)",
                                    {"calls": 0, "cost": 0.0})
        o["calls"] += 1; o["cost"] = round(o["cost"] + r["cost_usd"], 6)

    return {
        "period": period, "since": since or "(all time)",
        "calls": len(rows),
        "total_cost": round(total_cost, 4),
        "input_tokens": total_in, "output_tokens": total_out,
        "by_provider": by_provider, "by_operation": by_operation,
        "avg_cost_per_call": round(total_cost / len(rows), 6) if rows else 0.0,
    }


def format_cost_text(rep: dict) -> str:
    """Render the cost report as console-friendly plain text."""
    lines = ["=" * 60, f"API COST REPORT - {rep['period']} (since {rep['since']})",
             "=" * 60,
             f"  Total cost      : ${rep['total_cost']:.4f}",
             f"  API calls       : {rep['calls']}",
             f"  Tokens          : {rep['input_tokens']:,} in / "
             f"{rep['output_tokens']:,} out",
             f"  Avg cost / call : ${rep['avg_cost_per_call']:.5f}"]
    if rep["by_provider"]:
        lines.append("\n  By provider:")
        for prov, d in sorted(rep["by_provider"].items()):
            lines.append(f"    {prov:14} {d['calls']:>4} calls   ${d['cost']:.4f}")
    if rep["by_operation"]:
        lines.append("\n  By operation:")
        for op, d in sorted(rep["by_operation"].items(),
                            key=lambda kv: -kv[1]["cost"]):
            lines.append(f"    {op:24} {d['calls']:>4} calls   ${d['cost']:.4f}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_cost_html(rep: dict) -> str:
    """Render the cost report as an HTML block for email reports."""
    rows = "".join(
        f"<tr><td>{op}</td><td align=right>{d['calls']}</td>"
        f"<td align=right>${d['cost']:.4f}</td></tr>"
        for op, d in sorted(rep["by_operation"].items(),
                            key=lambda kv: -kv[1]["cost"]))
    return (
        f"<h3>🔌 API Costs ({rep['period']})</h3>"
        f"<p><b>Total: ${rep['total_cost']:.4f}</b> across {rep['calls']} calls "
        f"({rep['input_tokens']:,} in / {rep['output_tokens']:,} out tokens)</p>"
        f"<table cellpadding=4 style='border-collapse:collapse'>"
        f"<tr><th align=left>Operation</th><th>Calls</th><th>Cost</th></tr>"
        f"{rows}</table>")
