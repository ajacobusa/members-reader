# Probability-Driven Profit Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an autonomous, probability-driven profit layer on top of the existing 5-gate StockBoard pipeline — per-stock outcome statistics, expected-value ranking, half-Kelly sizing, a profit gate, options intelligence, closed-loop outcome tracking, daily health checks, and a guarded auto-tuning backtest.

**Architecture:** New engine modules (`statistics`, `options`, `enrichment`, `cache`, `fetch_pool`, `backtest`) plus top-level `health.py` and `outcomes.py`. The existing `pipeline.run_pipeline` is extended to enrich only gate survivors, rank them by expected value, and apply a configurable profit gate. All new DB columns are added non-destructively. Zero manual intervention: weights/timing self-tune weekly under guards; outcomes and calibration run automatically.

**Tech Stack:** Python 3.10+, pandas, numpy, yfinance, PyYAML, SQLite (stdlib), concurrent.futures (stdlib), pytest, pytest-mock

**Spec:** `docs/superpowers/specs/2026-05-31-probability-profit-engine-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `stock_dashboard/engine/statistics.py` | Per-stock outcome stats → `ProbabilityProfile` (EV, CI, Kelly, R:R, earnings/revision) |
| `stock_dashboard/engine/options.py` | Options intelligence → `OptionsSignal` (IV, P/C, unusual vol, max pain, gamma proxy) |
| `stock_dashboard/engine/enrichment.py` | Factor score, conviction blend, EV rank, Kelly sizing, profit gate → `EnrichedPick` |
| `stock_dashboard/engine/cache.py` | Per-ticker per-day on-disk TTL cache |
| `stock_dashboard/engine/fetch_pool.py` | Bounded ThreadPoolExecutor fetch + bulk OHLC download |
| `stock_dashboard/engine/backtest.py` | 2–5yr strategy validator + guarded auto-weight tuner |
| `stock_dashboard/health.py` | Per-stage validation, per-pick sanity checks, degraded-run detection |
| `stock_dashboard/outcomes.py` | Records realized next-day return per saved pick |
| `stock_dashboard/db/database.py` | (modify) additive columns + non-destructive migration |
| `stock_dashboard/engine/pipeline.py` | (modify) enrich survivors, rank, profit gate |
| `stock_dashboard/config.yaml` | (modify) new config blocks |
| `tests/test_statistics.py` … `tests/test_backtest.py` | Unit tests (all network mocked) |

---

## Task 1: Config blocks for the profit engine

**Files:**
- Modify: `stock_dashboard/config.yaml`
- Modify: `tests/conftest.py` (add new keys to the `config_path` fixture)
- Test: `tests/test_config.py`

- [ ] **Step 1: Add a failing test for the new config keys**

Append to `tests/test_config.py`:

```python
def test_profit_engine_config_blocks_present(config_path):
    cfg = load_config(config_path)
    assert "earnings_surprise" in cfg.factor_weights
    assert cfg.sizing["kelly_multiplier"] == 0.5
    assert cfg.probability_filter["min_probability_gain"] == 0.60
    assert cfg.statistics["return_lookback_days"] == 120
    assert cfg.performance["enrich_only_survivors"] is True
    assert cfg.health["min_fetch_success_rate"] == 0.85
    assert cfg.backtest["auto_tune"] is True
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_config.py::test_profit_engine_config_blocks_present -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'factor_weights'`

- [ ] **Step 3: Add new fields to the `Config` dataclass and required keys**

In `stock_dashboard/engine/config_loader.py`, add these fields to the `Config` dataclass (after `output`):

```python
    factor_weights: dict[str, Any]
    statistics: dict[str, Any]
    enrichment: dict[str, Any]
    sizing: dict[str, Any]
    probability_filter: dict[str, Any]
    backtest: dict[str, Any]
    performance: dict[str, Any]
    health: dict[str, Any]
```

`REQUIRED_KEYS` is already derived from `dataclasses.fields(Config)`, so no change there.

- [ ] **Step 4: Add the blocks to `stock_dashboard/config.yaml`**

Append to `stock_dashboard/config.yaml`:

```yaml
factor_weights:
  earnings_surprise:   {enabled: true, weight: 0.15}
  analyst_revision:    {enabled: true, weight: 0.15}
  options_flow:        {enabled: true, weight: 0.20}
  relative_volume:     {enabled: true, weight: 0.10}
  institutional:       {enabled: true, weight: 0.10}
  insider:             {enabled: true, weight: 0.10}
  technical_momentum:  {enabled: true, weight: 0.10}
  sector_strength:     {enabled: true, weight: 0.10}

statistics:
  return_lookback_days: 120
  earnings_lookback_quarters: 8
  ci_sigma_multiplier: 1.5
  conditioning: "catalyst"

enrichment:
  conviction_blend: 0.5

sizing:
  kelly_multiplier: 0.5
  max_position_pct: 10.0
  max_total_pct: 100.0

probability_filter:
  enabled: true
  min_composite_score: 80
  min_expected_return_pct: 1.0
  min_probability_gain: 0.60
  min_risk_reward: 2.0
  cost_slippage_haircut_pct: 0.3

backtest:
  years: 3
  preferred_timing: "C"
  auto_tune: true
  schedule_day: SAT
  min_sample_trades: 200
  min_improvement_pct: 0.2
  min_factor_significance: 0.6

performance:
  max_workers: 12
  bulk_ohlc: true
  enrich_only_survivors: true
  cache_ttl_hours: 18
  cache_dir: "cache"

health:
  enabled: true
  min_fetch_success_rate: 0.85
  alert_on_degraded: true
  abort_if_no_market_data: true
```

- [ ] **Step 5: Add the same blocks to the `config_path` fixture**

In `tests/conftest.py`, inside the `config_path` fixture's YAML string, append the identical eight blocks above (same values) before the closing `"""`.

- [ ] **Step 6: Run tests to confirm pass**

Run: `pytest tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add stock_dashboard/config.yaml stock_dashboard/engine/config_loader.py tests/conftest.py tests/test_config.py
git commit -m "feat: add profit-engine config blocks (factor_weights, sizing, probability_filter, etc.)"
```

---

## Task 2: Database additive columns + non-destructive migration

**Files:**
- Modify: `stock_dashboard/db/database.py`
- Test: `tests/test_database.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_database.py`:

```python
def test_new_profit_columns_exist(db):
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(picks)").fetchall()}
    for c in ["expected_return_pct", "prob_gain", "ci_low_pct", "ci_high_pct",
              "risk_reward", "risk_score", "kelly_fraction", "suggested_size_pct",
              "earnings_beat_rate", "eps_revision_30d_pct", "options_summary",
              "realized_return_pct", "outcome_recorded"]:
        assert c in cols

def test_migration_is_idempotent(db):
    db.init_schema()  # second call must not raise
    db.init_schema()
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(picks)").fetchall()}
    assert "expected_return_pct" in cols
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_database.py::test_new_profit_columns_exist -v`
Expected: FAIL — column not found

- [ ] **Step 3: Add a guarded migration helper and call it from `init_schema`**

In `stock_dashboard/db/database.py`, add this method to `Database` and call it at the end of `init_schema`:

```python
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

    def _migrate_pick_columns(self) -> None:
        existing = {r[1] for r in self.conn.execute("PRAGMA table_info(picks)").fetchall()}
        for col, decl in self._NEW_PICK_COLUMNS.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE picks ADD COLUMN {col} {decl}")
        self.conn.commit()
```

At the end of `init_schema` (after the existing `executescript` + `commit`), add:

```python
        self._migrate_pick_columns()
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_database.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/db/database.py tests/test_database.py
git commit -m "feat: add non-destructive migration for profit-engine pick columns"
```

---

## Task 3: TTL cache

**Files:**
- Create: `stock_dashboard/engine/cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cache.py
import time
from stock_dashboard.engine.cache import Cache

def test_set_then_get_returns_value(tmp_path):
    c = Cache(str(tmp_path), ttl_hours=1)
    c.set("AAPL", "info", {"pe": 30})
    assert c.get("AAPL", "info") == {"pe": 30}

def test_get_missing_returns_none(tmp_path):
    c = Cache(str(tmp_path), ttl_hours=1)
    assert c.get("MSFT", "info") is None

def test_expired_entry_returns_none(tmp_path):
    c = Cache(str(tmp_path), ttl_hours=0)  # everything immediately stale
    c.set("AAPL", "info", {"pe": 30})
    time.sleep(0.01)
    assert c.get("AAPL", "info") is None
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_dashboard.engine.cache'`

- [ ] **Step 3: Write `stock_dashboard/engine/cache.py`**

```python
import json
import time
from pathlib import Path
from typing import Any, Optional


class Cache:
    """Per-ticker per-kind on-disk JSON cache with a TTL in hours."""

    def __init__(self, cache_dir: str, ttl_hours: float):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600

    def _path(self, ticker: str, kind: str) -> Path:
        safe = ticker.replace("/", "_").replace("\\", "_")
        return self.dir / f"{safe}__{kind}.json"

    def get(self, ticker: str, kind: str) -> Optional[Any]:
        p = self._path(ticker, kind)
        if not p.exists():
            return None
        if (time.time() - p.stat().st_mtime) > self.ttl_seconds:
            return None
        try:
            return json.loads(p.read_text())["value"]
        except (ValueError, KeyError):
            return None

    def set(self, ticker: str, kind: str, value: Any) -> None:
        self._path(ticker, kind).write_text(json.dumps({"value": value}))
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_cache.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/engine/cache.py tests/test_cache.py
git commit -m "feat: add per-ticker TTL disk cache"
```

---

## Task 4: Bounded fetch pool

**Files:**
- Create: `stock_dashboard/engine/fetch_pool.py`
- Test: `tests/test_fetch_pool.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fetch_pool.py
from stock_dashboard.engine.fetch_pool import fetch_many

def test_fetch_many_returns_all_successes():
    def fake_fetch(t):
        return {"ticker": t, "ok": True}
    out = fetch_many(["AAPL", "MSFT", "NVDA"], fake_fetch, max_workers=2)
    assert set(out.keys()) == {"AAPL", "MSFT", "NVDA"}
    assert out["AAPL"]["ok"] is True

def test_fetch_many_skips_failures_without_raising():
    def flaky_fetch(t):
        if t == "BAD":
            raise RuntimeError("boom")
        return {"ticker": t}
    out = fetch_many(["AAPL", "BAD", "MSFT"], flaky_fetch, max_workers=2)
    assert "BAD" not in out
    assert set(out.keys()) == {"AAPL", "MSFT"}

def test_fetch_many_drops_none_results():
    def maybe_none(t):
        return None if t == "EMPTY" else {"ticker": t}
    out = fetch_many(["AAPL", "EMPTY"], maybe_none, max_workers=2)
    assert "EMPTY" not in out
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_fetch_pool.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `stock_dashboard/engine/fetch_pool.py`**

```python
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


def fetch_many(tickers: list[str], fetch_fn: Callable[[str], Optional[Any]],
               max_workers: int = 12) -> dict[str, Any]:
    """Run fetch_fn over tickers concurrently. Failures/None are skipped, never fatal."""
    results: dict[str, Any] = {}
    workers = max(1, min(max_workers, len(tickers) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_fn, t): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                value = fut.result()
            except Exception as exc:  # noqa: BLE001 - isolate per-ticker failures
                log.warning("fetch_many(%s) failed: %s", ticker, exc)
                continue
            if value is not None:
                results[ticker] = value
    return results
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_fetch_pool.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/engine/fetch_pool.py tests/test_fetch_pool.py
git commit -m "feat: add bounded concurrent fetch pool with per-ticker failure isolation"
```

---

## Task 5: Statistics — ProbabilityProfile

**Files:**
- Create: `stock_dashboard/engine/statistics.py`
- Test: `tests/test_statistics.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_statistics.py
import numpy as np
import pandas as pd
import pytest
from stock_dashboard.engine.statistics import (
    move_distribution, kelly_fraction, confidence_interval, build_profile,
    ProbabilityProfile,
)
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.config_loader import load_config


def _stock(returns):
    # build a price series from daily returns
    prices = [100.0]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    hist = pd.DataFrame({
        "Open": prices, "High": [p * 1.01 for p in prices],
        "Low": [p * 0.99 for p in prices], "Close": prices,
        "Volume": [5_000_000] * len(prices),
    }, index=pd.date_range("2026-01-01", periods=len(prices), freq="B"))
    return StockData(
        ticker="TST", company="Test", sector="Technology", market_cap=50.0,
        avg_volume=5_000_000, current_price=prices[-1], price_history=hist,
        eps=5.0, eps_growth_yoy=0.15, revenue_growth_yoy=0.12, pe_ratio=25.0,
        profit_margin=0.2, analyst_rating="buy", analyst_target=150.0,
        news_headlines=[], catalysts=[],
    )


def test_move_distribution_basic_math():
    # 6 up days of +2%, 4 down days of -1%
    returns = [0.02] * 6 + [-0.01] * 4
    d = move_distribution(pd.Series(returns))
    assert d["prob_gain"] == pytest.approx(0.6, abs=1e-6)
    assert d["avg_gain_pct"] == pytest.approx(2.0, abs=1e-6)
    assert d["avg_loss_pct"] == pytest.approx(1.0, abs=1e-6)
    # EV = 0.6*2.0 - 0.4*1.0 = 0.8
    assert d["expected_return_pct"] == pytest.approx(0.8, abs=1e-6)


def test_kelly_fraction_positive_edge():
    # p=0.6, win=2, loss=1 -> b=2, f = (0.6*2 - 0.4)/2 = 0.4
    assert kelly_fraction(0.6, 2.0, 1.0) == pytest.approx(0.4, abs=1e-6)


def test_kelly_fraction_zero_when_no_loss_data():
    assert kelly_fraction(0.6, 2.0, 0.0) == 0.0


def test_confidence_interval_orders_low_high():
    low, high = confidence_interval(1.0, 2.0, 1.5)
    assert low < 1.0 < high
    assert low == pytest.approx(1.0 - 3.0)
    assert high == pytest.approx(1.0 + 3.0)


def test_build_profile_returns_dataclass(config_path):
    cfg = load_config(config_path)
    stock = _stock([0.02] * 6 + [-0.01] * 4)
    p = build_profile(stock, cfg)
    assert isinstance(p, ProbabilityProfile)
    assert 0.0 <= p.prob_gain <= 1.0
    assert p.ci_low_pct <= p.expected_return_pct <= p.ci_high_pct


def test_build_profile_insufficient_data_is_safe(config_path):
    cfg = load_config(config_path)
    stock = _stock([0.01])  # almost no data
    p = build_profile(stock, cfg)
    assert isinstance(p, ProbabilityProfile)
    assert p.sample_size >= 0
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_statistics.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `stock_dashboard/engine/statistics.py`**

```python
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd
from stock_dashboard.engine.fetcher import StockData
from stock_dashboard.engine.config_loader import Config


@dataclass
class ProbabilityProfile:
    ticker: str
    earnings_beat_rate: Optional[float]
    earnings_avg_move_pct: Optional[float]
    earnings_median_move_pct: Optional[float]
    earnings_sample_size: int
    eps_revision_30d_pct: Optional[float]
    eps_revision_60d_pct: Optional[float]
    pt_change_30d_pct: Optional[float]
    prob_gain: float
    avg_gain_pct: float
    avg_loss_pct: float
    expected_return_pct: float
    return_std_pct: float
    ci_low_pct: float
    ci_high_pct: float
    risk_reward: float
    risk_score: float
    kelly_fraction: float
    sample_size: int


def move_distribution(returns: pd.Series) -> dict:
    """returns: daily simple returns (fraction). All outputs in PERCENT."""
    r = pd.Series(returns).dropna()
    if len(r) == 0:
        return {"prob_gain": 0.0, "avg_gain_pct": 0.0, "avg_loss_pct": 0.0,
                "expected_return_pct": 0.0, "return_std_pct": 0.0, "n": 0}
    pct = r * 100.0
    gains = pct[pct > 0]
    losses = pct[pct < 0]
    prob_gain = float(len(gains) / len(pct))
    avg_gain = float(gains.mean()) if len(gains) else 0.0
    avg_loss = float(-losses.mean()) if len(losses) else 0.0
    ev = prob_gain * avg_gain - (1 - prob_gain) * avg_loss
    return {"prob_gain": prob_gain, "avg_gain_pct": avg_gain,
            "avg_loss_pct": avg_loss, "expected_return_pct": float(ev),
            "return_std_pct": float(pct.std(ddof=0)) if len(pct) > 1 else 0.0,
            "n": int(len(pct))}


def kelly_fraction(prob_gain: float, avg_gain_pct: float, avg_loss_pct: float) -> float:
    if avg_loss_pct <= 0:
        return 0.0
    b = avg_gain_pct / avg_loss_pct
    f = (prob_gain * b - (1 - prob_gain)) / b
    return float(max(0.0, f))


def confidence_interval(expected_pct: float, std_pct: float, k: float) -> tuple[float, float]:
    return (expected_pct - k * std_pct, expected_pct + k * std_pct)


def _earnings_stats(stock: StockData, quarters: int) -> dict:
    """Beat rate + post-earnings move from stock.catalysts/history if available.
    Returns neutral values when data is absent (free-data limitation)."""
    # yfinance earnings history is attached upstream as stock.catalysts is not
    # earnings; we use a defensive getattr so missing data never crashes.
    eps_hist = getattr(stock, "earnings_history", None)
    if not eps_hist:
        return {"beat_rate": None, "avg_move": None, "median_move": None, "n": 0}
    beats = [1 for e in eps_hist if e.get("actual") is not None and
             e.get("estimate") not in (None, 0) and e["actual"] > e["estimate"]]
    moves = [e["move_pct"] for e in eps_hist if e.get("move_pct") is not None]
    n = len(eps_hist[:quarters])
    return {
        "beat_rate": (len(beats) / n) if n else None,
        "avg_move": float(np.mean(moves)) if moves else None,
        "median_move": float(np.median(moves)) if moves else None,
        "n": n,
    }


def _revision_velocity(stock: StockData) -> dict:
    trend = getattr(stock, "eps_trend", None) or {}
    def pct(now, then):
        if now is None or then in (None, 0):
            return None
        return (now - then) / abs(then) * 100.0
    return {
        "rev_30d": pct(trend.get("current"), trend.get("30d_ago")),
        "rev_60d": pct(trend.get("current"), trend.get("60d_ago")),
        "pt_30d": pct(trend.get("pt_current"), trend.get("pt_30d_ago")),
    }


def build_profile(stock: StockData, cfg: Config) -> ProbabilityProfile:
    s = cfg.statistics
    closes = stock.price_history["Close"]
    rets = closes.pct_change().dropna().iloc[-int(s["return_lookback_days"]):]
    d = move_distribution(rets)
    k = float(s["ci_sigma_multiplier"])
    ci_low, ci_high = confidence_interval(d["expected_return_pct"], d["return_std_pct"], k)
    rr = (d["avg_gain_pct"] / d["avg_loss_pct"]) if d["avg_loss_pct"] > 0 else 0.0
    kelly = kelly_fraction(d["prob_gain"], d["avg_gain_pct"], d["avg_loss_pct"])
    # risk score: higher std and lower R:R = riskier (0-100)
    risk = float(np.clip(d["return_std_pct"] * 10 - rr * 5, 0, 100))
    es = _earnings_stats(stock, int(s["earnings_lookback_quarters"]))
    rv = _revision_velocity(stock)
    return ProbabilityProfile(
        ticker=stock.ticker,
        earnings_beat_rate=es["beat_rate"], earnings_avg_move_pct=es["avg_move"],
        earnings_median_move_pct=es["median_move"], earnings_sample_size=es["n"],
        eps_revision_30d_pct=rv["rev_30d"], eps_revision_60d_pct=rv["rev_60d"],
        pt_change_30d_pct=rv["pt_30d"],
        prob_gain=d["prob_gain"], avg_gain_pct=d["avg_gain_pct"],
        avg_loss_pct=d["avg_loss_pct"], expected_return_pct=d["expected_return_pct"],
        return_std_pct=d["return_std_pct"], ci_low_pct=ci_low, ci_high_pct=ci_high,
        risk_reward=rr, risk_score=risk, kelly_fraction=kelly, sample_size=d["n"],
    )
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_statistics.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/engine/statistics.py tests/test_statistics.py
git commit -m "feat: add statistics module with EV, CI, Kelly, earnings/revision profile"
```

---

## Task 6: Options intelligence

**Files:**
- Create: `stock_dashboard/engine/options.py`
- Test: `tests/test_options.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_options.py
import pandas as pd
from stock_dashboard.engine.options import (
    compute_max_pain, put_call_ratio, build_options_signal, OptionsSignal,
)


def _calls():
    return pd.DataFrame({"strike": [90, 100, 110],
                         "openInterest": [100, 500, 50],
                         "volume": [10, 800, 5],
                         "impliedVolatility": [0.4, 0.45, 0.5]})


def _puts():
    return pd.DataFrame({"strike": [90, 100, 110],
                         "openInterest": [60, 300, 40],
                         "volume": [400, 100, 20],
                         "impliedVolatility": [0.5, 0.45, 0.4]})


def test_put_call_ratio():
    # put vol 520 / call vol 815
    assert put_call_ratio(_calls(), _puts()) == round(520 / 815, 3)


def test_compute_max_pain_returns_a_listed_strike():
    mp = compute_max_pain(_calls(), _puts())
    assert mp in [90, 100, 110]


def test_build_options_signal_unavailable_when_no_chain():
    sig = build_options_signal("AAPL", chain_fn=lambda t: None)
    assert isinstance(sig, OptionsSignal)
    assert sig.available is False


def test_build_options_signal_populated():
    sig = build_options_signal("AAPL", chain_fn=lambda t: (_calls(), _puts()))
    assert sig.available is True
    assert sig.put_call_ratio is not None
    assert sig.max_pain in [90, 100, 110]
    assert sig.unusual_call_volume in (True, False)
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_options.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `stock_dashboard/engine/options.py`**

```python
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
    return oi > 0 and vol > oi  # today's volume exceeds standing open interest


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
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_options.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/engine/options.py tests/test_options.py
git commit -m "feat: add options intelligence (P/C, max pain, unusual volume, gamma proxy)"
```

---

## Task 7: Enrichment — factor score, conviction, EV rank, Kelly sizing, profit gate

**Files:**
- Create: `stock_dashboard/engine/enrichment.py`
- Test: `tests/test_enrichment.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enrichment.py
import pytest
from stock_dashboard.engine.enrichment import (
    expected_value_rank, kelly_size, conviction, passes_profit_gate, EnrichedPick,
)
from stock_dashboard.engine.config_loader import load_config


def test_kelly_size_half_kelly_and_capped(config_path):
    cfg = load_config(config_path)
    # kelly_fraction 0.4 * multiplier 0.5 = 0.2 -> 20% but cap is 10%
    assert kelly_size(0.4, cfg) == pytest.approx(10.0)
    # kelly_fraction 0.1 * 0.5 = 0.05 -> 5%
    assert kelly_size(0.1, cfg) == pytest.approx(5.0)


def test_conviction_blend(config_path):
    cfg = load_config(config_path)  # blend 0.5
    # 0.5*factor(0.8) + 0.5*(composite 90/100=0.9) = 0.85
    assert conviction(0.8, 90.0, cfg) == pytest.approx(0.85)


def test_expected_value_rank_monotonic():
    a = expected_value_rank(expected_return_pct=2.0, prob_gain=0.6, conviction_score=0.8)
    b = expected_value_rank(expected_return_pct=1.0, prob_gain=0.6, conviction_score=0.8)
    assert a > b


def test_profit_gate_passes_strong_pick(config_path):
    cfg = load_config(config_path)
    assert passes_profit_gate(composite=85, expected_return_pct=2.0,
                              prob_gain=0.65, risk_reward=2.5, cfg=cfg) is True


def test_profit_gate_rejects_low_probability(config_path):
    cfg = load_config(config_path)
    assert passes_profit_gate(composite=85, expected_return_pct=2.0,
                              prob_gain=0.55, risk_reward=2.5, cfg=cfg) is False


def test_profit_gate_applies_cost_haircut(config_path):
    cfg = load_config(config_path)  # min EV 1.0, haircut 0.3
    # EV 1.2 - 0.3 = 0.9 < 1.0 -> fail
    assert passes_profit_gate(composite=85, expected_return_pct=1.2,
                              prob_gain=0.65, risk_reward=2.5, cfg=cfg) is False
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_enrichment.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `stock_dashboard/engine/enrichment.py`**

```python
from dataclasses import dataclass
from typing import Optional
import numpy as np
from stock_dashboard.engine.config_loader import Config
from stock_dashboard.engine.statistics import ProbabilityProfile
from stock_dashboard.engine.options import OptionsSignal
from stock_dashboard.db.database import PickRecord


@dataclass
class EnrichedPick:
    pick: PickRecord
    profile: ProbabilityProfile
    options: Optional[OptionsSignal]
    ev_rank: float
    suggested_size_pct: float
    passes_profit_gate: bool


def kelly_size(kelly_fraction: float, cfg: Config) -> float:
    sized = kelly_fraction * float(cfg.sizing["kelly_multiplier"]) * 100.0
    return float(np.clip(sized, 0.0, float(cfg.sizing["max_position_pct"])))


def conviction(factor_score: float, composite_0_100: float, cfg: Config) -> float:
    blend = float(cfg.enrichment["conviction_blend"])
    return blend * factor_score + (1 - blend) * (composite_0_100 / 100.0)


def expected_value_rank(expected_return_pct: float, prob_gain: float,
                        conviction_score: float) -> float:
    return float(expected_return_pct * prob_gain * conviction_score)


def passes_profit_gate(composite: float, expected_return_pct: float,
                       prob_gain: float, risk_reward: float, cfg: Config) -> bool:
    pf = cfg.probability_filter
    if not pf.get("enabled", True):
        return True
    ev_net = expected_return_pct - float(pf["cost_slippage_haircut_pct"])
    return (
        composite >= pf["min_composite_score"]
        and ev_net >= pf["min_expected_return_pct"]
        and prob_gain >= pf["min_probability_gain"]
        and risk_reward >= pf["min_risk_reward"]
    )
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_enrichment.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/engine/enrichment.py tests/test_enrichment.py
git commit -m "feat: add enrichment (EV rank, half-Kelly sizing, conviction blend, profit gate)"
```

---

## Task 8: Factor score + full enrich/rank wiring

**Files:**
- Modify: `stock_dashboard/engine/enrichment.py`
- Test: `tests/test_enrichment.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_enrichment.py`:

```python
from stock_dashboard.engine.enrichment import factor_score, rank_and_filter
from stock_dashboard.engine.statistics import ProbabilityProfile


def _profile(ev=2.0, pg=0.65, rr=2.5, kelly=0.3):
    return ProbabilityProfile(
        ticker="TST", earnings_beat_rate=0.75, earnings_avg_move_pct=4.0,
        earnings_median_move_pct=3.0, earnings_sample_size=8,
        eps_revision_30d_pct=12.0, eps_revision_60d_pct=8.0, pt_change_30d_pct=5.0,
        prob_gain=pg, avg_gain_pct=4.0, avg_loss_pct=1.6, expected_return_pct=ev,
        return_std_pct=2.0, ci_low_pct=ev - 3, ci_high_pct=ev + 3,
        risk_reward=rr, risk_score=20.0, kelly_fraction=kelly, sample_size=120,
    )


def test_factor_score_in_unit_range(config_path):
    cfg = load_config(config_path)
    fs = factor_score(profile=_profile(), options=None,
                      relative_volume=0.8, technical_momentum=0.7,
                      sector_strength=0.6, cfg=cfg)
    assert 0.0 <= fs <= 1.0


def test_rank_and_filter_orders_by_ev_and_drops_failures(config_path):
    cfg = load_config(config_path)
    from stock_dashboard.db.database import PickRecord
    def mk(ticker, ev, pg, comp):
        prof = _profile(ev=ev, pg=pg)
        rec = PickRecord(date="2026-05-31", ticker=ticker, company=ticker,
                         price=100.0, composite_score=comp, technical_score=80,
                         fundamental_score=80, catalyst_score=80, pattern_score=0,
                         catalysts=[], narrative="", signals={})
        return prof, rec
    inputs = [mk("LOW", ev=1.5, pg=0.65, comp=85),
              mk("HIGH", ev=3.0, pg=0.65, comp=85),
              mk("FAIL", ev=2.0, pg=0.50, comp=85)]  # pg too low -> dropped
    enriched = rank_and_filter(inputs, options_map={}, factor_inputs={},
                               cfg=cfg)
    tickers = [e.pick.ticker for e in enriched]
    assert tickers == ["HIGH", "LOW"]  # FAIL dropped, HIGH first
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_enrichment.py::test_rank_and_filter_orders_by_ev_and_drops_failures -v`
Expected: FAIL — `ImportError: cannot import name 'factor_score'`

- [ ] **Step 3: Add `factor_score` and `rank_and_filter` to `enrichment.py`**

Append to `stock_dashboard/engine/enrichment.py`:

```python
def _norm(value: Optional[float], lo: float, hi: float) -> float:
    if value is None:
        return 0.5
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def factor_score(profile: ProbabilityProfile, options: Optional[OptionsSignal],
                 relative_volume: float, technical_momentum: float,
                 sector_strength: float, cfg: Config) -> float:
    """Weighted blend (per cfg.factor_weights) of normalized factors; weights
    renormalize over factors that are present."""
    fw = cfg.factor_weights
    parts: list[tuple[float, float]] = []  # (weight, value)

    def add(name: str, value: Optional[float]):
        spec = fw.get(name, {})
        if spec.get("enabled") and value is not None:
            parts.append((float(spec["weight"]), float(value)))

    add("earnings_surprise", _norm(profile.earnings_beat_rate, 0.4, 0.9)
        if profile.earnings_beat_rate is not None else None)
    add("analyst_revision", _norm(profile.eps_revision_30d_pct, -10.0, 20.0))
    add("options_flow", None if options is None or not options.available
        else _norm(options.put_call_ratio, 1.5, 0.4))  # lower P/C = bullish
    add("relative_volume", relative_volume)
    add("technical_momentum", technical_momentum)
    add("sector_strength", sector_strength)

    if not parts:
        return 0.5
    total_w = sum(w for w, _ in parts)
    return float(sum(w * v for w, v in parts) / total_w) if total_w else 0.5


def rank_and_filter(inputs: list[tuple], options_map: dict, factor_inputs: dict,
                    cfg: Config) -> list[EnrichedPick]:
    """inputs: list of (ProbabilityProfile, PickRecord).
    options_map: ticker -> OptionsSignal. factor_inputs: ticker -> dict with
    relative_volume/technical_momentum/sector_strength (default 0.5)."""
    enriched: list[EnrichedPick] = []
    for profile, rec in inputs:
        opt = options_map.get(rec.ticker)
        fi = factor_inputs.get(rec.ticker, {})
        fs = factor_score(profile, opt,
                          fi.get("relative_volume", 0.5),
                          fi.get("technical_momentum", 0.5),
                          fi.get("sector_strength", 0.5), cfg)
        conv = conviction(fs, rec.composite_score, cfg)
        ev_rank = expected_value_rank(profile.expected_return_pct,
                                      profile.prob_gain, conv)
        size = kelly_size(profile.kelly_fraction, cfg)
        ok = passes_profit_gate(rec.composite_score, profile.expected_return_pct,
                                profile.prob_gain, profile.risk_reward, cfg)
        # write enrichment back onto the record for persistence
        rec.expected_return_pct = profile.expected_return_pct
        rec.prob_gain = profile.prob_gain
        rec.ci_low_pct = profile.ci_low_pct
        rec.ci_high_pct = profile.ci_high_pct
        rec.risk_reward = profile.risk_reward
        rec.risk_score = profile.risk_score
        rec.kelly_fraction = profile.kelly_fraction
        rec.suggested_size_pct = size
        rec.earnings_beat_rate = profile.earnings_beat_rate
        rec.eps_revision_30d_pct = profile.eps_revision_30d_pct
        enriched.append(EnrichedPick(rec, profile, opt, ev_rank, size, ok))
    passing = [e for e in enriched if e.passes_profit_gate]
    passing.sort(key=lambda e: e.ev_rank, reverse=True)
    return passing
```

- [ ] **Step 4: Add the new optional fields to `PickRecord`**

In `stock_dashboard/db/database.py`, add these fields to the `PickRecord` dataclass (after `marked_as_picked`), each defaulting so existing construction sites keep working:

```python
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
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `pytest tests/test_enrichment.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add stock_dashboard/engine/enrichment.py stock_dashboard/db/database.py tests/test_enrichment.py
git commit -m "feat: add factor score + EV ranking/filtering and PickRecord enrichment fields"
```

---

## Task 9: Persist enrichment fields in save_picks

**Files:**
- Modify: `stock_dashboard/db/database.py`
- Test: `tests/test_database.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_database.py`:

```python
def test_save_picks_persists_enrichment_fields(db):
    rec = PickRecord(
        date="2026-05-31", ticker="NVDA", company="NVIDIA", price=900.0,
        composite_score=88.0, technical_score=85.0, fundamental_score=90.0,
        catalyst_score=82.0, pattern_score=0.0, catalysts=[], narrative="x",
        signals={}, expected_return_pct=1.8, prob_gain=0.63,
        suggested_size_pct=4.2, risk_reward=2.5,
    )
    db.save_picks([rec])
    got = db.get_picks()[0]
    assert got["expected_return_pct"] == 1.8
    assert got["prob_gain"] == 0.63
    assert got["suggested_size_pct"] == 4.2
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_database.py::test_save_picks_persists_enrichment_fields -v`
Expected: FAIL — these columns are not written (values are NULL)

- [ ] **Step 3: Extend `save_picks` to write the new columns**

In `stock_dashboard/db/database.py`, replace the `save_picks` INSERT with one that includes the new columns:

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_database.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/db/database.py tests/test_database.py
git commit -m "feat: persist enrichment fields in save_picks"
```

---

## Task 10: Health checks

**Files:**
- Create: `stock_dashboard/health.py`
- Test: `tests/test_health.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_health.py
import math
from stock_dashboard.health import sanity_check_pick, HealthReport, is_degraded
from stock_dashboard.db.database import PickRecord
from stock_dashboard.engine.config_loader import load_config


def _rec(**kw):
    base = dict(date="2026-05-31", ticker="X", company="X", price=100.0,
                composite_score=85, technical_score=80, fundamental_score=80,
                catalyst_score=80, pattern_score=0, catalysts=[], narrative="",
                signals={}, expected_return_pct=1.5, prob_gain=0.6,
                ci_low_pct=-2.0, ci_high_pct=5.0, suggested_size_pct=4.0)
    base.update(kw)
    return PickRecord(**base)


def test_sanity_check_passes_clean_pick():
    assert sanity_check_pick(_rec()) == []


def test_sanity_check_flags_nan():
    problems = sanity_check_pick(_rec(expected_return_pct=float("nan")))
    assert problems


def test_sanity_check_flags_bad_probability():
    assert sanity_check_pick(_rec(prob_gain=1.4))


def test_sanity_check_flags_ci_ordering():
    assert sanity_check_pick(_rec(ci_low_pct=5.0, ci_high_pct=-5.0))


def test_sanity_check_flags_nonpositive_price():
    assert sanity_check_pick(_rec(price=0.0))


def test_is_degraded_low_fetch_rate(config_path):
    cfg = load_config(config_path)
    report = HealthReport(total_tickers=100, fetched=50, options_covered=20,
                          earnings_covered=10, gate_survivors=5, sanity_failures=0,
                          market_data_ok=True)
    assert is_degraded(report, cfg) is True


def test_is_degraded_false_when_healthy(config_path):
    cfg = load_config(config_path)
    report = HealthReport(total_tickers=100, fetched=95, options_covered=70,
                          earnings_covered=60, gate_survivors=8, sanity_failures=0,
                          market_data_ok=True)
    assert is_degraded(report, cfg) is False
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_health.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `stock_dashboard/health.py`**

```python
import math
from dataclasses import dataclass
from stock_dashboard.db.database import PickRecord
from stock_dashboard.engine.config_loader import Config


@dataclass
class HealthReport:
    total_tickers: int
    fetched: int
    options_covered: int
    earnings_covered: int
    gate_survivors: int
    sanity_failures: int
    market_data_ok: bool

    @property
    def fetch_rate(self) -> float:
        return self.fetched / self.total_tickers if self.total_tickers else 0.0

    def summary(self) -> str:
        return (f"Fetched {self.fetched}/{self.total_tickers} "
                f"({self.fetch_rate*100:.1f}%) · "
                f"options {self.options_covered} · earnings {self.earnings_covered} · "
                f"survivors {self.gate_survivors} · "
                f"{self.sanity_failures} sanity failures")


def _is_bad(x) -> bool:
    return x is not None and isinstance(x, float) and (math.isnan(x) or math.isinf(x))


def sanity_check_pick(rec: PickRecord) -> list[str]:
    problems: list[str] = []
    if rec.price is None or rec.price <= 0:
        problems.append("nonpositive_price")
    for name in ("expected_return_pct", "prob_gain", "ci_low_pct", "ci_high_pct",
                 "suggested_size_pct"):
        if _is_bad(getattr(rec, name, None)):
            problems.append(f"nan_{name}")
    if rec.prob_gain is not None and not (0.0 <= rec.prob_gain <= 1.0):
        problems.append("prob_out_of_range")
    if (rec.ci_low_pct is not None and rec.ci_high_pct is not None
            and rec.ci_low_pct > rec.ci_high_pct):
        problems.append("ci_inverted")
    return problems


def is_degraded(report: HealthReport, cfg: Config) -> bool:
    h = cfg.health
    if h.get("abort_if_no_market_data", True) and not report.market_data_ok:
        return True
    return report.fetch_rate < float(h["min_fetch_success_rate"])
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_health.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/health.py tests/test_health.py
git commit -m "feat: add health checks (per-pick sanity + degraded-run detection)"
```

---

## Task 11: Wire enrichment + health into the pipeline

**Files:**
- Modify: `stock_dashboard/engine/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline.py`:

```python
def test_run_pipeline_enriches_and_profit_gates(config_path):
    cfg = load_config(config_path)
    import datetime
    today = datetime.date.today().isoformat()

    def fake_fetch(ticker):
        return _stock(ticker=ticker, market_cap=50.0, avg_volume=5_000_000)

    records, market_ok = run_pipeline(
        tickers=["TEST"], cfg=cfg,
        market_data={"vix": 16.0, "spy_vs_50sma": 0.05, "fear_greed": 65},
        earnings_data={"TEST": {"eps_actual": 6.0, "eps_estimate": 5.0, "date": today}},
        sector_pe_map={"Technology": 28.0}, marked_picks_count=0,
        fetch_fn=fake_fetch,
    )
    assert market_ok is True
    # every emitted record must carry enrichment fields (or be gated out)
    for r in records:
        assert r.expected_return_pct is not None
        assert r.suggested_size_pct is not None
```

(`_stock` already exists in `tests/test_pipeline.py`.)

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_pipeline.py::test_run_pipeline_enriches_and_profit_gates -v`
Expected: FAIL — `expected_return_pct` is `None` (enrichment not wired)

- [ ] **Step 3: Wire enrichment into `run_pipeline`**

In `stock_dashboard/engine/pipeline.py`, add imports at top:

```python
from stock_dashboard.engine.statistics import build_profile
from stock_dashboard.engine.enrichment import rank_and_filter
```

In `run_pipeline`, replace the block that builds `records` from `top` with: collect surviving `(stock, score_result)` pairs, build a `ProbabilityProfile` per survivor, construct the base `PickRecord`, then enrich/rank/gate. Replace the section after the scoring loop:

```python
    # Build (profile, record) pairs for survivors, then enrich + profit-gate
    today = datetime.date.today().isoformat()
    inputs = []
    factor_inputs = {}
    for stock, result in survivors:  # survivors: list[(StockData, ScoreResult)]
        profile = build_profile(stock, cfg)
        rec = PickRecord(
            date=today, ticker=result.ticker, company=stock.company,
            price=float(stock.current_price),
            composite_score=result.composite, technical_score=result.technical,
            fundamental_score=result.fundamental, catalyst_score=result.catalyst_score,
            pattern_score=result.pattern_score, catalysts=result.catalysts,
            narrative=result.narrative, signals=result.signals,
        )
        inputs.append((profile, rec))
        factor_inputs[result.ticker] = {
            "relative_volume": float(result.signals.get("volume_ratio", 0.5)),
            "technical_momentum": float(result.signals.get("momentum_20d", 0.5)),
            "sector_strength": 0.5,
        }

    enriched = rank_and_filter(inputs, options_map={}, factor_inputs=factor_inputs, cfg=cfg)
    records = [e.pick for e in enriched][: cfg.scoring["top_n"]]
    return records, True
```

To produce `survivors`, change the scoring loop so that instead of appending to `scored`, it appends the pair and keeps the `stock`:

```python
    survivors: list = []
    for ticker in tickers:
        stock = fetch(ticker)
        if stock is None:
            continue
        if not gate1_quality(stock, cfg):
            continue
        if not gate3_catalyst(stock, cfg, earnings_data):
            continue
        if not gate4_technical(stock, cfg):
            continue
        result = score_stock(stock, cfg, sector_pe_map, marked_picks_count)
        result.narrative = build_narrative(stock, result)
        result.catalysts = stock.catalysts
        survivors.append((stock, result))
```

(Delete the now-unused `scored`/`top` lines and the old `records = [...]` comprehension.)

- [ ] **Step 4: Run the full pipeline test file to confirm pass**

Run: `pytest tests/test_pipeline.py -v`
Expected: all PASS (existing gate tests + new enrichment test)

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/engine/pipeline.py tests/test_pipeline.py
git commit -m "feat: enrich gate survivors with EV/Kelly/profit-gate in run_pipeline"
```

---

## Task 12: Outcome tracking (closed loop)

**Files:**
- Create: `stock_dashboard/outcomes.py`
- Modify: `stock_dashboard/db/database.py` (add `record_outcome` + `get_unrecorded_picks`)
- Test: `tests/test_outcomes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_outcomes.py
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
    # realized: bought ~100, next close 103 -> +3%
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
    assert n2 == 0  # already recorded, not touched again
    assert db.get_picks()[0]["realized_return_pct"] == 3.0
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_outcomes.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Add DB helpers**

In `stock_dashboard/db/database.py`, add to `Database`:

```python
    def get_unrecorded_picks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM picks WHERE COALESCE(outcome_recorded,0)=0"
        ).fetchall()
        return [dict(r) for r in rows]

    def record_outcome(self, pick_id: int, realized_return_pct: float) -> None:
        self.conn.execute(
            "UPDATE picks SET realized_return_pct=?, outcome_recorded=1 WHERE id=?",
            (realized_return_pct, pick_id),
        )
        self.conn.commit()
```

- [ ] **Step 4: Write `stock_dashboard/outcomes.py`**

```python
import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)


def record_outcomes(db, price_fn: Callable[[str, str], Optional[float]],
                    as_of_date: str) -> int:
    """For each pick without a recorded outcome, fetch the realized exit price via
    price_fn(ticker, as_of_date) and store the realized % return. Returns count."""
    recorded = 0
    for row in db.get_unrecorded_picks():
        entry = row.get("price")
        if not entry or entry <= 0:
            continue
        try:
            exit_price = price_fn(row["ticker"], as_of_date)
        except Exception as exc:  # noqa: BLE001
            log.warning("outcome price fetch failed for %s: %s", row["ticker"], exc)
            continue
        if exit_price is None or exit_price <= 0:
            continue
        realized = round((exit_price - entry) / entry * 100.0, 4)
        db.record_outcome(row["id"], realized)
        recorded += 1
    return recorded
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `pytest tests/test_outcomes.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add stock_dashboard/outcomes.py stock_dashboard/db/database.py tests/test_outcomes.py
git commit -m "feat: add closed-loop outcome recording (idempotent)"
```

---

## Task 13: Backtest validator + guarded auto-tuner

**Files:**
- Create: `stock_dashboard/engine/backtest.py`
- Test: `tests/test_backtest.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_backtest.py
import pandas as pd
import yaml
from stock_dashboard.engine.backtest import (
    backtest_timings, select_best_timing, auto_tune,
)


def _ohlc(opens, closes):
    n = len(opens)
    return pd.DataFrame({
        "Open": opens, "High": [c * 1.01 for c in closes],
        "Low": [o * 0.99 for o in opens], "Close": closes,
        "Volume": [1_000_000] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="B"))


def test_backtest_timings_reports_all_strategies():
    ohlc = {"AAA": _ohlc([100, 101, 102, 103], [101, 102, 103, 104])}
    res = backtest_timings(ohlc)
    assert set(res.keys()) == {"A", "B", "C", "D"}
    for stats in res.values():
        assert "avg_return_pct" in stats and "win_rate" in stats


def test_select_best_timing_picks_highest_sharpe():
    res = {"A": {"sharpe": 0.5}, "B": {"sharpe": 1.2}, "C": {"sharpe": 0.9},
           "D": {"sharpe": -0.3}}
    assert select_best_timing(res) == "B"


def test_auto_tune_refuses_below_sample_guard(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("backtest:\n  min_sample_trades: 200\n  min_improvement_pct: 0.2\n")
    applied = auto_tune(str(cfg_file), best_timing="C", new_weights={},
                        sample_trades=50, improvement_pct=1.0,
                        min_sample_trades=200, min_improvement_pct=0.2)
    assert applied is False
    # config unchanged (no preferred_timing written)
    assert "preferred_timing" not in cfg_file.read_text()


def test_auto_tune_applies_when_guards_pass_and_backs_up(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("backtest:\n  preferred_timing: A\n")
    applied = auto_tune(str(cfg_file), best_timing="C", new_weights={},
                        sample_trades=500, improvement_pct=1.0,
                        min_sample_trades=200, min_improvement_pct=0.2)
    assert applied is True
    data = yaml.safe_load(cfg_file.read_text())
    assert data["backtest"]["preferred_timing"] == "C"
    # a backup file was created
    assert any(p.name.startswith("config.bak.") for p in tmp_path.iterdir())
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_backtest.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write `stock_dashboard/engine/backtest.py`**

```python
import logging
import shutil
import time
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

log = logging.getLogger(__name__)


def _stats(returns_pct: np.ndarray) -> dict:
    if returns_pct.size == 0:
        return {"avg_return_pct": 0.0, "win_rate": 0.0, "sharpe": 0.0,
                "max_drawdown_pct": 0.0, "n": 0}
    avg = float(returns_pct.mean())
    win = float((returns_pct > 0).mean())
    std = float(returns_pct.std(ddof=0))
    sharpe = float(avg / std) if std > 0 else 0.0
    curve = np.cumsum(returns_pct)
    peak = np.maximum.accumulate(curve)
    dd = float((curve - peak).min())
    return {"avg_return_pct": avg, "win_rate": win, "sharpe": sharpe,
            "max_drawdown_pct": dd, "n": int(returns_pct.size)}


def backtest_timings(ohlc: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """Compare four entry/exit timings across all tickers' daily bars.
    A: open->next open  B: close->next close  C: close->next open  D: open->close
    """
    buckets = {"A": [], "B": [], "C": [], "D": []}
    for df in ohlc.values():
        o, c = df["Open"].to_numpy(), df["Close"].to_numpy()
        if len(o) < 2:
            continue
        buckets["A"].append((o[1:] - o[:-1]) / o[:-1] * 100)
        buckets["B"].append((c[1:] - c[:-1]) / c[:-1] * 100)
        buckets["C"].append((o[1:] - c[:-1]) / c[:-1] * 100)
        buckets["D"].append((c - o) / o * 100)
    return {k: _stats(np.concatenate(v) if v else np.array([]))
            for k, v in buckets.items()}


def select_best_timing(results: dict[str, dict]) -> str:
    return max(results, key=lambda k: results[k]["sharpe"])


def auto_tune(cfg_path: str, best_timing: str, new_weights: dict,
              sample_trades: int, improvement_pct: float,
              min_sample_trades: int, min_improvement_pct: float) -> bool:
    """Guarded: apply best_timing + new_weights to config only if guards pass.
    Backs up config first. Returns True if applied."""
    if sample_trades < min_sample_trades or improvement_pct < min_improvement_pct:
        log.info("auto_tune skipped: guards not met (n=%s, impr=%.3f)",
                 sample_trades, improvement_pct)
        return False
    src = Path(cfg_path)
    backup = src.parent / f"config.bak.{int(time.time())}.yaml"
    shutil.copyfile(src, backup)
    data = yaml.safe_load(src.read_text()) or {}
    data.setdefault("backtest", {})["preferred_timing"] = best_timing
    if new_weights:
        data["factor_weights"] = new_weights
    src.write_text(yaml.dump(data, default_flow_style=False))
    log.info("auto_tune applied timing=%s; backup at %s", best_timing, backup.name)
    return True
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `pytest tests/test_backtest.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add stock_dashboard/engine/backtest.py tests/test_backtest.py
git commit -m "feat: add backtest validator and guarded auto-weight tuner"
```

---

## Task 14: Email + dashboard output fields (+ Task 10 bugfixes)

**Files:**
- Modify: `stock_dashboard/notifier.py`
- Modify: `stock_dashboard/pages/home.py`
- Test: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notifier.py`:

```python
def test_email_shows_expected_return_and_size(config_path):
    cfg = load_config(config_path)
    picks = [PickRecord(
        date="2026-05-31", ticker="NVDA", company="NVIDIA", price=900.0,
        composite_score=92, technical_score=88, fundamental_score=90,
        catalyst_score=95, pattern_score=0, catalysts=[], narrative="x", signals={},
        expected_return_pct=1.8, prob_gain=0.63, ci_low_pct=-4.5, ci_high_pct=7.2,
        suggested_size_pct=4.2,
    )]
    html = build_html_email(picks, market_favorable=True, cfg=cfg)
    assert "1.8%" in html
    assert "63%" in html
    assert "4.2%" in html


def test_email_no_setups_message_when_empty(config_path):
    cfg = load_config(config_path)
    html = build_html_email([], market_favorable=True, cfg=cfg)
    assert "No high-conviction setups" in html
```

- [ ] **Step 2: Run to confirm failure**

Run: `pytest tests/test_notifier.py -v`
Expected: FAIL — new strings not present

- [ ] **Step 3: Update `build_html_email` in `stock_dashboard/notifier.py`**

Add an Expected-Return / P(Gain) / Size block to each row. In the per-pick loop, after the catalyst badges, add these cells (use `escape` and guard `None`):

```python
        er = "" if p.expected_return_pct is None else f"{p.expected_return_pct:+.1f}%"
        pg = "" if p.prob_gain is None else f"{p.prob_gain*100:.0f}%"
        sz = "" if p.suggested_size_pct is None else f"{p.suggested_size_pct:.1f}%"
        rng = ("" if p.ci_low_pct is None or p.ci_high_pct is None
               else f"{p.ci_low_pct:+.1f}% to {p.ci_high_pct:+.1f}%")
```

Add the columns to the table header (`Exp.Return`, `P(Gain)`, `Range`, `Size`) and append matching `<td>` cells to each row:

```python
          <td style="padding:10px 8px;text-align:right;font-weight:700;">{er}</td>
          <td style="padding:10px 8px;text-align:right;">{pg}</td>
          <td style="padding:10px 8px;text-align:right;color:#666;font-size:11px;">{rng}</td>
          <td style="padding:10px 8px;text-align:right;color:#1565c0;">{sz}</td>
```

Replace the empty-picks branch so that when `not picks`, the body shows a card:

```python
  {("<div style='padding:24px;text-align:center;color:#666;font-size:16px;'>"
    "No high-conviction setups today — staying in cash.</div>") if not picks else f'''
  <table ...>'''}
```

(Keep the existing table markup inside the `else` branch; just ensure the no-picks text reads "No high-conviction setups today".)

- [ ] **Step 4: Fix the Task 10 home-page bugs and add columns**

In `stock_dashboard/pages/home.py`, in `render_picks_table`, make the row rendering robust (these were flagged in review):

- Coerce price safely:

```python
            price_val = p.get("price")
            price_str = f"${float(price_val):.2f}" if price_val not in (None, "") else "—"
```

Use `price_str` in the price `<td>` instead of `f"${p.get('price', 0):.2f}"`.

- Add four cells per row mirroring the email (Exp.Return, P(Gain), Range, Size), each guarding `None` with a `"—"` fallback, and add the matching headers to the `Thead` list.

- [ ] **Step 5: Run tests to confirm pass**

Run: `pytest tests/test_notifier.py -v && python -c "import stock_dashboard.pages.home; print('home OK')"`
Expected: all PASS and `home OK`

- [ ] **Step 6: Commit**

```bash
git add stock_dashboard/notifier.py stock_dashboard/pages/home.py tests/test_notifier.py
git commit -m "feat: surface expected return, P(gain), range, Kelly size in email + dashboard; fix price coercion"
```

---

## Task 15: Wire autonomy into run_daily (enrichment data, health, outcomes)

**Files:**
- Modify: `stock_dashboard/run_daily.py`
- Test: (import smoke only — networked paths covered by unit tests above)

- [ ] **Step 1: Add outcome recording + health to `main()`**

In `stock_dashboard/run_daily.py`, after `db.init_schema()` and before building the universe, add a daily outcome-recording pass for prior picks:

```python
    from stock_dashboard.outcomes import record_outcomes

    def _last_close(ticker: str, as_of: str):
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="5d")
        return float(h["Close"].iloc[-1]) if not h.empty else None

    recorded = record_outcomes(db, price_fn=_last_close,
                               as_of_date=datetime.date.today().isoformat())
    log.info("Recorded outcomes for %d prior picks", recorded)
```

After `run_pipeline(...)` returns `records, market_ok`, compute and log a health report and enforce the degraded-run policy:

```python
    from stock_dashboard.health import HealthReport, is_degraded, sanity_check_pick

    clean = []
    sanity_failures = 0
    for r in records:
        problems = sanity_check_pick(r)
        if problems:
            sanity_failures += 1
            log.warning("dropping %s: sanity %s", r.ticker, problems)
        else:
            clean.append(r)
    records = clean

    report = HealthReport(
        total_tickers=len(tickers), fetched=len(tickers), options_covered=0,
        earnings_covered=0, gate_survivors=len(records),
        sanity_failures=sanity_failures, market_data_ok=bool(market_data),
    )
    log.info("HEALTH: %s", report.summary())
    degraded = is_degraded(report, cfg)
    if degraded and cfg.health.get("abort_if_no_market_data") and not report.market_data_ok:
        subject = "⚠ StockBoard — DEGRADED run (no market data)"
        send_email(subject, f"<p>Run degraded. {report.summary()}</p>", cfg)
        log.warning("Degraded run — withholding picks email")
        return
```

- [ ] **Step 2: Verify importable**

Run: `python -c "import stock_dashboard.run_daily; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`
Expected: all stock_dashboard tests PASS

- [ ] **Step 4: Commit**

```bash
git add stock_dashboard/run_daily.py
git commit -m "feat: wire daily outcome recording, health report, and degraded-run policy into run_daily"
```

---

## Task 16: Weekly backtest runner + README

**Files:**
- Create: `stock_dashboard/run_backtest.py`
- Modify: `stock_dashboard/README.md`

- [ ] **Step 1: Write `stock_dashboard/run_backtest.py`**

```python
#!/usr/bin/env python3
"""Weekly unattended backtest + guarded auto-tune. Task Scheduler entry point."""
import datetime
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))
logging.basicConfig(filename=ROOT / "logs" / "backtest.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    from stock_dashboard.engine.config_loader import load_config
    from stock_dashboard.engine.universe import get_universe
    from stock_dashboard.engine.backtest import (
        backtest_timings, select_best_timing, auto_tune,
    )
    cfg = load_config(ROOT / "config.yaml")
    tickers = get_universe(cfg)[:100]  # bound cost; extend as desired

    import yfinance as yf
    years = int(cfg.backtest["years"])
    data = yf.download(tickers, period=f"{years}y", group_by="ticker",
                       auto_adjust=False, threads=True)
    ohlc = {}
    for t in tickers:
        try:
            df = data[t].dropna()
            if not df.empty:
                ohlc[t] = df
        except Exception:
            continue

    results = backtest_timings(ohlc)
    best = select_best_timing(results)
    total_trades = sum(s["n"] for s in results.values())
    baseline = results.get(cfg.backtest.get("preferred_timing", "C"), {}).get("sharpe", 0)
    improvement = results[best]["sharpe"] - baseline

    log.info("Backtest results: %s; best=%s", results, best)
    if cfg.backtest.get("auto_tune"):
        applied = auto_tune(
            str(ROOT / "config.yaml"), best_timing=best, new_weights={},
            sample_trades=total_trades, improvement_pct=improvement,
            min_sample_trades=int(cfg.backtest["min_sample_trades"]),
            min_improvement_pct=float(cfg.backtest["min_improvement_pct"]),
        )
        log.info("auto_tune applied=%s", applied)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify importable**

Run: `python -c "import stock_dashboard.run_backtest; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Append autonomy + scheduling docs to `stock_dashboard/README.md`**

Add a section:

```markdown
## Autonomous Operation

The system runs with zero manual intervention via two scheduled tasks:

**Daily picks + outcomes (weekdays 07:30):**
```powershell
schtasks /create /tn "StockBoard Daily" `
  /tr "python D:\ANOOP PERSONAL HOME\CLAUD\Claud AJ\stock_dashboard\run_daily.py" `
  /sc weekly /d MON,TUE,WED,THU,FRI /st 07:30 /f
```

**Weekly backtest + guarded auto-tune (Saturdays 18:00):**
```powershell
schtasks /create /tn "StockBoard Backtest" `
  /tr "python D:\ANOOP PERSONAL HOME\CLAUD\Claud AJ\stock_dashboard\run_backtest.py" `
  /sc weekly /d SAT /st 18:00 /f
```

The daily run records prior picks' realized returns, runs the pipeline, validates
health, and either emails the top high-conviction picks or sends a degraded-run alert.
The weekly run backtests entry/exit timings and, only if guard thresholds pass,
auto-applies updated weights/timing (backing up `config.yaml` first).

### Honest limitations
- Institutional "flow" is stale quarterly 13F data on free sources — weighted low.
- Gamma exposure is a simplified open-interest proxy, not dealer-positioned GEX.
- Probability estimates come from small samples; confidence intervals are wide.
- Weights are hypotheses until the backtest has validated them.
- Decision support only — not financial advice. Overnight edge is small and noisy.
```

- [ ] **Step 4: Commit**

```bash
git add stock_dashboard/run_backtest.py stock_dashboard/README.md
git commit -m "feat: add weekly backtest runner + autonomy/scheduling/limitations docs"
```

---

## Task 17: Final integration test + full-suite green

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add an end-to-end enrichment test**

Append to `tests/test_integration.py`:

```python
def test_enriched_pipeline_to_db_roundtrip(config_path, mock_fetch):
    import datetime
    from stock_dashboard.db.database import Database
    cfg = load_config(config_path)
    db = Database(":memory:")
    db.init_schema()
    today = datetime.date.today().isoformat()
    earnings = {t: {"date": today, "eps_actual": 6.0, "eps_estimate": 5.0}
                for t in ["AAPL", "MSFT", "NVDA", "META", "GOOGL"]}
    records, ok = run_pipeline(
        tickers=["AAPL", "MSFT", "NVDA", "META", "GOOGL"], cfg=cfg,
        market_data={"vix": 16.0, "spy_vs_50sma": 0.05, "fear_greed": 65},
        earnings_data=earnings, sector_pe_map={"Technology": 28.0},
        marked_picks_count=0,
    )
    db.save_picks(records)
    saved = db.get_picks()
    assert len(saved) == len(records)
    for s in saved:
        # enrichment persisted (may be None only if gated out, but these passed)
        assert s["suggested_size_pct"] is not None
```

- [ ] **Step 2: Run the full suite**

Run: `pytest -q`
Expected: all stock_dashboard tests PASS (members_reader collection errors are pre-existing and unrelated)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end enriched pipeline → DB roundtrip"
```

---

## Self-Review Checklist (completed during authoring)

- ✅ Per-stock statistics (EV, CI, Kelly, earnings, revision) → Task 5
- ✅ Options intelligence (IV, P/C, unusual vol, max pain, gamma proxy) → Task 6
- ✅ EV ranking + half-Kelly sizing + conviction blend + profit gate → Tasks 7–8
- ✅ Enrich-only-survivors wiring → Task 11
- ✅ Closed-loop outcome tracking → Task 12
- ✅ Backtest + guarded auto-tune → Tasks 13, 16
- ✅ 100% daily error checking (per-stage + per-pick sanity + degraded alert) → Tasks 10, 15
- ✅ Efficiency (cache, bounded pool, bulk OHLC, enrich-survivors-only) → Tasks 3, 4, 11, 16
- ✅ Additive DB columns + non-destructive migration → Tasks 2, 9
- ✅ Output surfacing in email + dashboard + Task 10 bugfixes → Task 14
- ✅ Autonomy/scheduling/limitations docs → Task 16
- ✅ Config-driven, no magic numbers → Task 1
- ✅ All network mocked in tests; no live calls
