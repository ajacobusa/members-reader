import pytest
import json
from stock_dashboard.db.database import Database, PickRecord

@pytest.fixture
def db():
    d = Database(":memory:")
    d.init_schema()
    return d

def test_init_schema_creates_tables(db):
    rows = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert "picks" in names
    assert "market_conditions" in names

def test_save_and_retrieve_pick(db):
    record = PickRecord(
        date="2026-05-25", ticker="AAPL", company="Apple Inc",
        price=192.5, composite_score=88.0, technical_score=85.0,
        fundamental_score=90.0, catalyst_score=82.0, pattern_score=0.0,
        catalysts=[{"type": "earnings_beat", "magnitude": 12.0}],
        narrative="Apple beat EPS by 12%.", signals={"rsi": 58.0},
    )
    db.save_picks([record])
    picks = db.get_picks()
    assert len(picks) == 1
    assert picks[0]["ticker"] == "AAPL"
    assert picks[0]["composite_score"] == 88.0

def test_mark_as_picked(db):
    record = PickRecord(
        date="2026-05-25", ticker="MSFT", company="Microsoft",
        price=421.0, composite_score=85.0, technical_score=80.0,
        fundamental_score=88.0, catalyst_score=79.0, pattern_score=0.0,
        catalysts=[], narrative="Analyst upgrade.", signals={},
    )
    db.save_picks([record])
    pick_id = db.get_picks()[0]["id"]
    db.mark_as_picked(pick_id)
    picks = db.get_picks()
    assert picks[0]["marked_as_picked"] == 1

def test_save_market_conditions(db):
    db.save_market_conditions("2026-05-25", vix=16.2, spy_vs_50sma=0.05,
                               fear_greed=68, market_favorable=True)
    row = db.get_market_conditions("2026-05-25")
    assert row["vix"] == 16.2
    assert row["market_favorable"] == 1

def test_get_picks_filter_by_date(db):
    for date in ["2026-05-24", "2026-05-25"]:
        db.save_picks([PickRecord(
            date=date, ticker="NVDA", company="NVIDIA",
            price=892.0, composite_score=94.0, technical_score=88.0,
            fundamental_score=91.0, catalyst_score=95.0, pattern_score=0.0,
            catalysts=[], narrative="Test.", signals={},
        )])
    picks = db.get_picks(date="2026-05-25")
    assert len(picks) == 1
    assert picks[0]["date"] == "2026-05-25"
