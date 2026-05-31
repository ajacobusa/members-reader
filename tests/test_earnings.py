import numpy as np
import pandas as pd
import datetime
from stock_dashboard.engine.earnings import parse_recent_earnings


def _df(rows):
    # rows: list of (date_str, reported_eps, eps_estimate) newest-first
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, _, _ in rows])
    return pd.DataFrame(
        {"Reported EPS": [r for _, r, _ in rows],
         "EPS Estimate": [e for _, _, e in rows]},
        index=idx,
    )


TODAY = datetime.date(2026, 5, 31)


def test_returns_most_recent_reported_within_lookback():
    df = _df([("2026-05-29", 6.0, 5.0), ("2026-02-28", 4.0, 4.2)])
    out = parse_recent_earnings(df, today=TODAY, lookback_days=5)
    assert out is not None
    assert out["eps_actual"] == 6.0
    assert out["eps_estimate"] == 5.0
    assert out["date"] == "2026-05-29"


def test_skips_nan_actual_and_uses_next_valid_within_window():
    # most recent row reported today but actual not yet populated (NaN)
    df = _df([("2026-05-31", np.nan, 5.0), ("2026-05-28", 6.0, 5.0)])
    out = parse_recent_earnings(df, today=TODAY, lookback_days=5)
    assert out is not None
    assert out["eps_actual"] == 6.0  # skipped the NaN row
    assert out["date"] == "2026-05-28"


def test_returns_none_when_no_report_in_window():
    df = _df([("2026-02-28", 4.0, 4.2)])  # too old
    assert parse_recent_earnings(df, today=TODAY, lookback_days=5) is None


def test_returns_none_for_empty_or_none():
    assert parse_recent_earnings(None, today=TODAY, lookback_days=5) is None
    assert parse_recent_earnings(pd.DataFrame(), today=TODAY, lookback_days=5) is None


def test_ignores_future_dates():
    df = _df([("2026-06-15", 7.0, 6.0), ("2026-05-30", 6.0, 5.0)])  # first is future
    out = parse_recent_earnings(df, today=TODAY, lookback_days=5)
    assert out["date"] == "2026-05-30"
    assert out["eps_actual"] == 6.0


def test_lookback_is_configurable():
    df = _df([("2026-05-20", 6.0, 5.0)])  # 11 days ago
    assert parse_recent_earnings(df, today=TODAY, lookback_days=5) is None
    out = parse_recent_earnings(df, today=TODAY, lookback_days=14)
    assert out is not None and out["eps_actual"] == 6.0
