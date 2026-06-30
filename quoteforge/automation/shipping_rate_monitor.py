"""Shipping-rate review agent — re-checks the shipping COST model so we never quietly
start losing money when Gelato changes its rates.

Gelato updates shipping rates regularly and there is no single public flat rate (it
varies by product, size, destination and which hub fills the order), so this agent:
  - reports the current per-product shipping cost we assume (high-end table + margin)
    and what the buyer pays for express, so the owner sees exactly the basis;
  - STALENESS: alerts when the rates haven't been re-verified against the Gelato
    dashboard in SHIPPING_RATES_REVIEW_DAYS — a recurring prompt to re-check current
    production+shipping costs and bump SHIPPING_COST_TABLE_JSON if they moved, then
    stamp it with `shipping-rate-check --reviewed`.
  (Live auto-compare against a Gelato shipping quote is a future hook once Gelato's
  quote API is wired; until then the staleness prompt is the safe review mechanism.)

ALERTS the owner when a review is due. Report-only — it never changes prices itself.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _ledger_path() -> Path:
    """Where the 'rates last reviewed' stamp lives (OUTPUT_DIR/shipping_rates_review.json)."""
    from quoteforge.config import OUTPUT_DIR
    return Path(OUTPUT_DIR) / "shipping_rates_review.json"


def last_reviewed() -> "str | None":
    """ISO date the owner last verified the rates, or None if never."""
    p = _ledger_path()
    if p.exists():
        try:
            return (json.loads(p.read_text(encoding="utf-8")) or {}).get("last_reviewed")
        except Exception as exc:  # noqa: BLE001
            logger.debug("shipping review ledger unreadable: %s", exc)
    return None


def mark_reviewed(when: "str | None" = None) -> str:
    """Stamp 'rates reviewed today' (after the owner re-checked the Gelato dashboard)."""
    when = when or datetime.now().date().isoformat()
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"last_reviewed": when}), encoding="utf-8")
    return when


def _days_since(iso: str) -> int:
    """Whole days since an ISO date string (huge number if unparseable)."""
    try:
        d = datetime.fromisoformat(iso)
        return (datetime.now().date() - d.date()).days
    except Exception:  # noqa: BLE001
        return 10 ** 6


def review_shipping_rates() -> dict:
    """Is the shipping-cost model still current? Returns {ok, stale, days_since,
    last_reviewed, summary, issues}. Not stale == ok."""
    from quoteforge.config import SHIPPING_RATES_REVIEW_DAYS
    from quoteforge.etsy.shipping_costs import cost_summary
    summary = cost_summary()
    lr = last_reviewed()
    days = _days_since(lr) if lr else None
    stale = (days is None) or (days >= int(SHIPPING_RATES_REVIEW_DAYS))
    issues = []
    if stale:
        when = f"{days} days ago" if days is not None else "never"
        issues.append(
            f"Shipping rates last verified {when} (threshold {SHIPPING_RATES_REVIEW_DAYS}d). "
            "Gelato updates rates regularly - re-check each product's current "
            "production+shipping cost in the Gelato dashboard, update "
            "SHIPPING_COST_TABLE_JSON if it changed, then run "
            "`python -m quoteforge.admin shipping-rate-check --reviewed`.")
    return {"ok": not stale, "stale": stale, "days_since": days,
            "last_reviewed": lr, "summary": summary, "issues": issues}


def format_review_text(r: dict) -> str:
    """Human-readable shipping-rate review."""
    from quoteforge.config import (SHIPPING_MARGIN_PCT, ADDITIONAL_ITEM_SHIP_FACTOR,
                                   EXPRESS_SHIP_MULT)
    lines = ["Shipping-rate review", "=" * 52,
             f"  margin +{SHIPPING_MARGIN_PCT:.0f}% | extra item x{ADDITIONAL_ITEM_SHIP_FACTOR} "
             f"| express x{EXPRESS_SHIP_MULT} | high-end estimates",
             f"  last reviewed: {r.get('last_reviewed') or 'never'}"
             + (f" ({r['days_since']}d ago)" if r.get("days_since") is not None else ""),
             "", "  Per-product shipping charged (1 item, incl. margin):"]
    for row in r.get("summary", []):
        lines.append(f"    {row['type']:<12} ${row['first_item']:>6.2f}  ->  "
                     f"charged ${row['charged_w_margin']:>6.2f}")
    if r.get("issues"):
        lines.append("")
        lines += [f"  [!] {i}" for i in r["issues"]]
    else:
        lines.append("\n  Rates recently reviewed — no action needed.")
    return "\n".join(lines)
