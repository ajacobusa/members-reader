"""Simulated P&L over closed picks — evidence of strategy performance, zero risk."""
from dataclasses import dataclass


@dataclass
class PaperTradingSummary:
    num_trades: int
    wins: int
    win_rate: float
    avg_return_pct: float
    total_pnl_usd: float
    capital_per_trade: float
    best_pct: float
    worst_pct: float


def summarize(closed_picks: list[dict], capital_per_trade: float = 5000.0
              ) -> PaperTradingSummary:
    """closed_picks: pick dicts (as from Database.get_picks). Only those with a
    non-null realized_return_pct are counted. Assumes a fixed dollar stake per trade."""
    returns = [float(p["realized_return_pct"]) for p in closed_picks
               if p.get("realized_return_pct") is not None]
    n = len(returns)
    if n == 0:
        return PaperTradingSummary(0, 0, 0.0, 0.0, 0.0, capital_per_trade, 0.0, 0.0)
    wins = sum(1 for r in returns if r > 0)
    total_pnl = round(sum(capital_per_trade * (r / 100.0) for r in returns), 2)
    return PaperTradingSummary(
        num_trades=n, wins=wins, win_rate=round(wins / n, 4),
        avg_return_pct=round(sum(returns) / n, 4), total_pnl_usd=total_pnl,
        capital_per_trade=capital_per_trade,
        best_pct=round(max(returns), 4), worst_pct=round(min(returns), 4),
    )


def summary_line(s: PaperTradingSummary) -> str:
    if s.num_trades == 0:
        return "Paper-trading: no closed trades yet — evidence accrues as picks resolve."
    sign = "+" if s.total_pnl_usd >= 0 else ""
    return (f"Paper-trading to date: {s.num_trades} closed trades · "
            f"win rate {s.win_rate*100:.0f}% · avg {s.avg_return_pct:+.2f}%/trade · "
            f"simulated P&L {sign}${s.total_pnl_usd:,.0f} "
            f"(at ${s.capital_per_trade:,.0f}/trade)")
