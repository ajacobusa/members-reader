"""Pure, testable parsing of yfinance earnings_dates into a recent-earnings dict."""
import datetime
import math
from typing import Optional
import pandas as pd


def parse_recent_earnings(earnings_df: Optional[pd.DataFrame],
                          today: datetime.date,
                          lookback_days: int) -> Optional[dict]:
    """Return {date, eps_actual, eps_estimate} for the most recent PAST earnings
    row (within lookback_days) that has a non-NaN Reported EPS. None if absent.

    earnings_df: yfinance Ticker.earnings_dates (DatetimeIndex, columns include
    'Reported EPS' and 'EPS Estimate'). Future-dated and NaN-actual rows are skipped.
    """
    if earnings_df is None or len(earnings_df) == 0:
        return None
    cutoff = today - datetime.timedelta(days=lookback_days)

    # Build (date, actual, estimate) for past rows within the window, newest first
    candidates = []
    for ts, row in earnings_df.iterrows():
        try:
            d = ts.date()
        except AttributeError:
            continue
        if d > today or d < cutoff:
            continue
        actual = row.get("Reported EPS")
        estimate = row.get("EPS Estimate")
        if actual is None or (isinstance(actual, float) and math.isnan(actual)):
            continue
        candidates.append((d, float(actual),
                           None if estimate is None or (isinstance(estimate, float)
                                                        and math.isnan(estimate))
                           else float(estimate)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)  # newest valid first
    d, actual, estimate = candidates[0]
    return {"date": d.isoformat(), "eps_actual": actual, "eps_estimate": estimate}
