"""Abandoned-customization recovery escalates 1h -> 24h -> 72h (was a single
1x touch). Each stage fires once; a converted design stops the sequence."""
from datetime import datetime, timedelta

from unittest.mock import patch


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    return db


def _abandon(db, email, listing, minutes_ago):
    db.save_customization(email, listing=listing, material="framed", wording="Hi")
    old = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()
    with db._conn() as c:
        c.execute("UPDATE abandoned_customizations SET updated_at=? "
                  "WHERE email=? AND listing=?", (old, email, listing))


def test_stages_escalate_over_time(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.automation.customization_recovery import pending_recoveries
    # 90 min old, stage 0 -> due for stage 1 (1h)
    _abandon(db, "a@b.com", "L1", 90)
    due = pending_recoveries()
    assert any(it["email"] == "a@b.com" and it["next_stage"] == 1 for it in due)


def test_each_stage_fires_once_then_advances(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.automation import customization_recovery as cr
    _abandon(db, "c@b.com", "L2", 90)            # past 1h
    r1 = cr.run_recovery(send=True)
    assert r1["sent"] == 1
    # Same item, still 90 min old -> NOT due again for stage 1 (already sent)
    r2 = cr.run_recovery(send=True)
    assert r2["sent"] == 0
    # Age it past 24h -> stage 2 fires
    old = (datetime.now() - timedelta(minutes=1500)).isoformat()
    with db._conn() as c:
        c.execute("UPDATE abandoned_customizations SET updated_at=? WHERE email=?",
                  (old, "c@b.com"))
    r3 = cr.run_recovery(send=True)
    assert r3["sent"] == 1


def test_converted_design_stops_escalation(tmp_path, monkeypatch):
    db = _seed(tmp_path, monkeypatch)
    from quoteforge.automation import customization_recovery as cr
    _abandon(db, "d@b.com", "L3", 5000)          # past all stages
    db.mark_customization("d@b.com", "L3", "converted")
    assert cr.run_recovery(send=True)["sent"] == 0
