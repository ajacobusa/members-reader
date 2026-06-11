"""Stooq price-history provider — the no-API-key backup for when Yahoo
Finance (yfinance) rate-limits or fails. Returns a DataFrame shaped exactly
like yfinance's .history(): a DatetimeIndex with Open/High/Low/Close/Volume
columns, so it is a drop-in replacement for the price path downstream.

Stooq daily CSV endpoint (no account, no key):
    https://stooq.com/q/d/l/?s=aapl.us&i=d
"""
import io
import logging
from typing import Optional
import pandas as pd
from stock_dashboard.engine import ratelimit

log = logging.getLogger(__name__)

# Approximate trading days per yfinance-style period string, for trimming.
_PERIOD_DAYS = {
    "1mo": 22, "2mo": 44, "3mo": 66, "6mo": 126,
    "1y": 252, "2y": 504, "5y": 1260, "max": 100_000,
}


def _stooq_symbol(ticker: str) -> str:
    """Map a US ticker to Stooq's symbol form (lowercase, .us suffix).
    BRK.B -> brk-b.us  (Stooq uses '-' for class shares)."""
    t = ticker.strip().lower().replace(".", "-")
    return t if "." in t else f"{t}.us"


def fetch_price_history(ticker: str, period: str = "3mo",
                        timeout: int = 8) -> Optional[pd.DataFrame]:
    """Daily OHLCV from Stooq, trimmed to `period`. None on any failure."""
    guard = ratelimit.get_guard()
    if guard and guard.is_cooling("stooq"):
        log.info("skip stooq %s — rate-limited (cooling)", ticker)
        return None
    sym = _stooq_symbol(ticker)
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        import requests
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200 or not r.text or r.text.startswith("<"):
            log.warning("stooq %s -> HTTP %s / non-CSV", sym, r.status_code)
            # A '<'-prefixed HTML body is Stooq's daily-download block page.
            if guard and (r.status_code == 429 or (r.text or "").startswith("<")):
                guard.mark("stooq", reason="download blocked / quota")
            return None
        df = pd.read_csv(io.StringIO(r.text))
        # Stooq returns "No data" as a single-cell body when symbol is unknown.
        if df.empty or "Close" not in df.columns or "Date" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
        df = df[keep].dropna(subset=["Close"])
        if df.empty:
            return None
        n = _PERIOD_DAYS.get(period, 66)
        return df.tail(n)
    except Exception as exc:  # noqa: BLE001
        log.warning("stooq fetch_price_history(%s) failed: %s", ticker, exc)
        return None
