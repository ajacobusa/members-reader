from stock_dashboard.paper_trading import summarize, summary_line, PaperTradingSummary


def _pick(realized):
    return {"ticker": "X", "realized_return_pct": realized, "outcome_recorded": 1}


def test_summarize_basic_pnl():
    closed = [_pick(2.0), _pick(-1.0), _pick(3.0)]  # +2%, -1%, +3% on $5000 each
    s = summarize(closed, capital_per_trade=5000.0)
    assert s.num_trades == 3
    assert s.wins == 2
    assert s.win_rate == round(2/3, 4)
    # pnl = 5000*(0.02 - 0.01 + 0.03) = 5000*0.04 = 200
    assert s.total_pnl_usd == 200.0
    assert s.avg_return_pct == round((2.0 - 1.0 + 3.0)/3, 4)
    assert s.best_pct == 3.0
    assert s.worst_pct == -1.0


def test_summarize_ignores_unrecorded_or_null():
    closed = [_pick(2.0), {"ticker": "Y", "realized_return_pct": None,
                           "outcome_recorded": 0}]
    s = summarize(closed, capital_per_trade=1000.0)
    assert s.num_trades == 1
    assert s.total_pnl_usd == 20.0


def test_summarize_empty_is_safe():
    s = summarize([], capital_per_trade=5000.0)
    assert s.num_trades == 0
    assert s.total_pnl_usd == 0.0
    assert s.win_rate == 0.0


def test_summary_line_mentions_pnl_and_trades():
    s = summarize([_pick(2.0), _pick(4.0)], capital_per_trade=5000.0)
    line = summary_line(s)
    assert "$" in line
    assert "2" in line  # 2 trades
