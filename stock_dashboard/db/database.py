import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class PickRecord:
    date: str
    ticker: str
    company: str
    price: float
    composite_score: float
    technical_score: float
    fundamental_score: float
    catalyst_score: float
    pattern_score: float
    catalysts: list
    narrative: str
    signals: dict
    marked_as_picked: bool = False
    expected_return_pct: Optional[float] = None
    prob_gain: Optional[float] = None
    ci_low_pct: Optional[float] = None
    ci_high_pct: Optional[float] = None
    risk_reward: Optional[float] = None
    risk_score: Optional[float] = None
    kelly_fraction: Optional[float] = None
    suggested_size_pct: Optional[float] = None
    earnings_beat_rate: Optional[float] = None
    eps_revision_30d_pct: Optional[float] = None
    options_summary: Optional[str] = None
    realized_return_pct: Optional[float] = None
    outcome_recorded: bool = False


class Database:
    _NEW_PICK_COLUMNS = {
        "expected_return_pct": "REAL",
        "prob_gain": "REAL",
        "ci_low_pct": "REAL",
        "ci_high_pct": "REAL",
        "risk_reward": "REAL",
        "risk_score": "REAL",
        "kelly_fraction": "REAL",
        "suggested_size_pct": "REAL",
        "earnings_beat_rate": "REAL",
        "eps_revision_30d_pct": "REAL",
        "options_summary": "TEXT",
        "realized_return_pct": "REAL",
        "outcome_recorded": "INTEGER DEFAULT 0",
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company TEXT,
                price REAL,
                composite_score REAL,
                technical_score REAL,
                fundamental_score REAL,
                catalyst_score REAL,
                pattern_score REAL,
                catalysts TEXT,
                narrative TEXT,
                signals TEXT,
                marked_as_picked INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS market_conditions (
                date TEXT PRIMARY KEY,
                vix REAL,
                spy_vs_50sma REAL,
                fear_greed INTEGER,
                market_favorable INTEGER
            );
        """)
        self.conn.commit()
        self._migrate_pick_columns()

    def _migrate_pick_columns(self) -> None:
        existing = {r[1] for r in self.conn.execute("PRAGMA table_info(picks)").fetchall()}
        for col, decl in self._NEW_PICK_COLUMNS.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE picks ADD COLUMN {col} {decl}")
        self.conn.commit()

    def save_picks(self, records: list[PickRecord]) -> None:
        self.conn.executemany(
            """INSERT INTO picks
               (date, ticker, company, price, composite_score, technical_score,
                fundamental_score, catalyst_score, pattern_score, catalysts,
                narrative, signals, marked_as_picked,
                expected_return_pct, prob_gain, ci_low_pct, ci_high_pct,
                risk_reward, risk_score, kelly_fraction, suggested_size_pct,
                earnings_beat_rate, eps_revision_30d_pct, options_summary,
                realized_return_pct, outcome_recorded)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(r.date, r.ticker, r.company, r.price, r.composite_score,
              r.technical_score, r.fundamental_score, r.catalyst_score,
              r.pattern_score, json.dumps(r.catalysts), r.narrative,
              json.dumps(r.signals), int(r.marked_as_picked),
              r.expected_return_pct, r.prob_gain, r.ci_low_pct, r.ci_high_pct,
              r.risk_reward, r.risk_score, r.kelly_fraction, r.suggested_size_pct,
              r.earnings_beat_rate, r.eps_revision_30d_pct, r.options_summary,
              r.realized_return_pct, int(bool(r.outcome_recorded)))
             for r in records],
        )
        self.conn.commit()

    def get_picks(self, date: Optional[str] = None,
                  ticker: Optional[str] = None,
                  marked_only: bool = False) -> list[dict]:
        query = "SELECT * FROM picks WHERE 1=1"
        params: list[Any] = []
        if date:
            query += " AND date = ?"
            params.append(date)
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if marked_only:
            query += " AND marked_as_picked = 1"
        query += " ORDER BY date DESC, composite_score DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def mark_as_picked(self, pick_id: int) -> None:
        self.conn.execute(
            "UPDATE picks SET marked_as_picked = 1 WHERE id = ?", (pick_id,)
        )
        self.conn.commit()

    def save_market_conditions(self, date: str, vix: float,
                                spy_vs_50sma: float, fear_greed: int,
                                market_favorable: bool) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO market_conditions
               (date, vix, spy_vs_50sma, fear_greed, market_favorable)
               VALUES (?,?,?,?,?)""",
            (date, vix, spy_vs_50sma, fear_greed, int(market_favorable)),
        )
        self.conn.commit()

    def get_market_conditions(self, date: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM market_conditions WHERE date = ?", (date,)
        ).fetchone()
        return dict(row) if row else None

    def get_marked_picks(self) -> list[dict]:
        return self.get_picks(marked_only=True)

    def get_unrecorded_picks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM picks WHERE COALESCE(outcome_recorded,0)=0"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_closed_picks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM picks WHERE outcome_recorded=1 "
            "AND realized_return_pct IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]

    def record_outcome(self, pick_id: int, realized_return_pct: float) -> None:
        self.conn.execute(
            "UPDATE picks SET realized_return_pct=?, outcome_recorded=1 WHERE id=?",
            (realized_return_pct, pick_id),
        )
        self.conn.commit()
