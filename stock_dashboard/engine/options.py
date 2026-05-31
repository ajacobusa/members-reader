import logging
from dataclasses import dataclass
from typing import Callable, Optional
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class OptionsSignal:
    ticker: str
    implied_volatility: Optional[float]
    put_call_ratio: Optional[float]
    unusual_call_volume: bool
    unusual_put_volume: bool
    max_pain: Optional[float]
    gamma_proxy: Optional[float]
    available: bool


def put_call_ratio(calls: pd.DataFrame, puts: pd.DataFrame) -> float:
    cv = float(calls["volume"].sum())
    pv = float(puts["volume"].sum())
    return round(pv / cv, 3) if cv > 0 else 0.0


def compute_max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> float:
    strikes = sorted(set(calls["strike"]) | set(puts["strike"]))
    best_strike, best_pain = strikes[0], None
    for s in strikes:
        call_pain = ((s - calls["strike"]).clip(lower=0) * calls["openInterest"]).sum()
        put_pain = ((puts["strike"] - s).clip(lower=0) * puts["openInterest"]).sum()
        total = float(call_pain + put_pain)
        if best_pain is None or total < best_pain:
            best_pain, best_strike = total, s
    return float(best_strike)


def _unusual(df: pd.DataFrame) -> bool:
    oi = float(df["openInterest"].sum())
    vol = float(df["volume"].sum())
    return oi > 0 and vol > oi


def _gamma_proxy(calls: pd.DataFrame, puts: pd.DataFrame) -> float:
    # SIMPLIFIED proxy: net call-minus-put open interest, NOT dealer-positioned GEX.
    return float(calls["openInterest"].sum() - puts["openInterest"].sum())


def build_options_signal(
    ticker: str,
    chain_fn: Callable[[str], Optional[tuple]] = None,
) -> OptionsSignal:
    """chain_fn(ticker) -> (calls_df, puts_df) | None. Defaults to yfinance."""
    if chain_fn is None:
        chain_fn = _yf_chain
    try:
        chain = chain_fn(ticker)
    except Exception as exc:  # noqa: BLE001
        log.warning("options chain fetch failed for %s: %s", ticker, exc)
        chain = None
    if not chain:
        return OptionsSignal(ticker, None, None, False, False, None, None, False)
    calls, puts = chain
    iv = float(pd.concat([calls["impliedVolatility"], puts["impliedVolatility"]]).mean())
    return OptionsSignal(
        ticker=ticker, implied_volatility=iv,
        put_call_ratio=put_call_ratio(calls, puts),
        unusual_call_volume=_unusual(calls), unusual_put_volume=_unusual(puts),
        max_pain=compute_max_pain(calls, puts),
        gamma_proxy=_gamma_proxy(calls, puts), available=True,
    )


def _yf_chain(ticker: str):
    import yfinance as yf
    t = yf.Ticker(ticker)
    exps = t.options
    if not exps:
        return None
    oc = t.option_chain(exps[0])
    return oc.calls, oc.puts
