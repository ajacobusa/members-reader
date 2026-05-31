from stock_dashboard.db.database import Database, PickRecord
from stock_dashboard.outcomes import record_outcomes


def _db():
    d = Database(":memory:")
    d.init_schema()
    return d


def test_record_outcomes_writes_realized_return():
    db = _db()
    db.save_picks([PickRecord(
        date="2026-05-28", ticker="AAPL", company="Apple", price=100.0,
        composite_score=85, technical_score=80, fundamental_score=80,
        catalyst_score=80, pattern_score=0, catalysts=[], narrative="", signals={},
    )])
    n = record_outcomes(db, price_fn=lambda t, d: 103.0, as_of_date="2026-05-29")
    assert n == 1
    rec = db.get_picks()[0]
    assert rec["realized_return_pct"] == 3.0
    assert rec["outcome_recorded"] == 1


def test_record_outcomes_is_idempotent():
    db = _db()
    db.save_picks([PickRecord(
        date="2026-05-28", ticker="AAPL", company="Apple", price=100.0,
        composite_score=85, technical_score=80, fundamental_score=80,
        catalyst_score=80, pattern_score=0, catalysts=[], narrative="", signals={},
    )])
    record_outcomes(db, price_fn=lambda t, d: 103.0, as_of_date="2026-05-29")
    n2 = record_outcomes(db, price_fn=lambda t, d: 110.0, as_of_date="2026-05-29")
    assert n2 == 0
    assert db.get_picks()[0]["realized_return_pct"] == 3.0
