# Stock Market Dashboard — Design Spec
**Date:** 2026-05-24  
**Status:** Approved for implementation

---

## Overview

A Python Dash web application that generates and displays daily top-10 stock buy recommendations for top-tier US equities (S&P 500 + NASDAQ 100). Each recommendation is catalyst-driven — a stock only appears if there is a concrete, verifiable reason it is the best buy *today*. The app also maintains a history log of past picks and uses that history to tune its scoring weights over time.

---

## Goals

- Surface the top 10 best-buy stocks each day from a universe of ~600 top-tier tickers
- Every pick must have a specific today-reason: earnings beat, analyst upgrade, volume breakout, guidance raise, or similar catalyst
- Display a rich "Why Buy Today" narrative per pick, assembled from multiple data sources
- Persist picks history in SQLite for reference and pattern learning
- Make every threshold, weight, and condition adjustable via `config.yaml` without touching code
- Work fully on free data sources (Tier A); optionally enhance with free API keys (Tier B)

---

## Architecture

### Framework & Runtime
- **Dash (Plotly)** — multi-page app, Python 3.10+
- **SQLite** — local persistence, zero infrastructure, single `.db` file
- **yfinance, finviz, feedparser, requests, beautifulsoup4** — data layer
- **pandas** — data processing and scoring
- **PyYAML** — config loading

### Project Layout

```
stock_dashboard/
├── app.py                  # Dash entry point, page registry
├── config.yaml             # All tunable parameters (no hardcoded values)
├── requirements.txt
├── pages/
│   ├── home.py             # Daily top-10 picks display
│   ├── history.py          # Past picks log and performance
│   └── settings.py         # Live weight/threshold adjustment UI
├── engine/
│   ├── universe.py         # S&P 500 + NASDAQ 100 ticker lists
│   ├── fetcher.py          # yfinance + Finviz + RSS + scraping wrapper
│   ├── sentiment.py        # Alpha Vantage / NewsAPI / Benzinga (Tier B)
│   ├── scorer.py           # Signal computation and composite scoring
│   ├── pipeline.py         # 5-gate orchestrator (recommender)
│   └── analyzer.py         # Pattern analysis from picks history
├── db/
│   ├── database.py         # SQLite schema, connection, CRUD
│   └── stocks.db           # Created on first run
└── assets/
    └── style.css
```

---

## Data Sources

### Tier A — No API Key Required

| Source | Data Provided | Library |
|--------|--------------|---------|
| **yfinance** | Price/volume history, earnings (actual vs estimate), analyst ratings & price targets, fundamentals (P/E, EPS, revenue, margins), upcoming earnings calendar, company news (7 days), institutional holdings | `yfinance` |
| **Finviz** | Stock screener, news headlines per ticker (48hrs), analyst Buy/Hold/Sell counts, insider trading signals, short interest %, relative sector performance | `finviz` |
| **RSS Feeds** | Reuters, MarketWatch, CNBC, Yahoo Finance, Seeking Alpha — market-moving headlines and earnings/upgrade stories | `feedparser` |
| **Web scraping** | CNN Fear & Greed Index (market sentiment), StockAnalysis.com (earnings history backup) | `requests`, `beautifulsoup4` |

### Tier B — Free API Keys (Optional)

| Source | Data Provided | Key Source |
|--------|--------------|------------|
| **Alpha Vantage** | News sentiment score per ticker (−1 to +1), topic tagging (earnings, M&A, macro), sentiment trend | alphavantage.co |
| **Benzinga** | Real-time analyst upgrade/downgrade alerts, price target changes, rating firm + analyst name, coverage initiations | benzinga.com/apis |
| **NewsAPI** | 80,000+ sources aggregated (WSJ, FT, Bloomberg), ticker keyword search, timestamp filtering | newsapi.org |

**Graceful degradation:** If a Tier B key is absent or blank in `config.yaml`, that source is silently skipped. The pick narrative is built from whatever sources are available. Quality degrades gracefully, never crashes.

---

## The 5-Gate Pipeline

Every stock in the universe passes through five gates in sequence. Failing any gate eliminates the stock from that day's picks. Gates run on-demand when the user clicks "Run Today's Picks."

### Gate 1 — Quality Filter (Top-Tier Only)
Eliminates low-quality stocks before any analysis. A stock passes if:
- Member of S&P 500 **or** NASDAQ 100
- Market cap > $10B
- Average daily volume > 1M shares
- Positive EPS (profitable)

### Gate 2 — Market Conditions
Checks the broad market environment. If the market is hostile, all picks are paused and the UI shows a "Market conditions unfavorable" banner. Conditions checked:
- VIX < 25 (configurable threshold)
- SPY and/or QQQ above their 50-day SMA
- Market breadth positive (advance/decline ratio)
- CNN Fear & Greed Index above configurable floor

### Gate 3 — Catalyst Check (Today-Reason Required)
The core gate. A stock **must** have at least one active catalyst from the list below. No catalyst = no pick, regardless of how good the technicals or fundamentals are.

Catalyst types (each configurable, can be enabled/disabled):
- **Earnings beat** — reported earnings in last N days (default: 3), EPS beat by > X% (default: 5%)
- **Analyst upgrade** — upgrade or new Buy/Strong Buy rating in last N days (default: 3)
- **Volume breakout** — today's volume > X× 20-day average (default: 2×)
- **52-week high breakout** — price closing at or above 52-week high
- **Guidance raised** — company raised forward guidance in last earnings call
- **Price target increase** — analyst raised price target significantly (default: > 10%)

### Gate 4 — Technical Setup
Confirms price action supports the catalyst — avoids chasing extended moves or catching falling knives:
- RSI between 40–70 (not overbought, not oversold)
- Price above 20-day SMA
- MACD bullish (signal line crossover or positive histogram)
- Price not more than 15% above 20-day SMA (not over-extended)

### Gate 5 — Score and Rank
Surviving stocks are scored on a 0–100 composite scale and the top 10 are selected.

**Scoring model (default weights, all configurable):**

| Component | Default Weight | Signals |
|-----------|---------------|---------|
| Technical | 35% | RSI position, MACD strength, momentum (20d), volume ratio, SMA crossover |
| Fundamental | 35% | EPS growth YoY, revenue growth YoY, P/E vs sector median, analyst consensus, profit margin |
| Catalyst strength | 20% | Type of catalyst, recency, magnitude of beat/upgrade |
| Pattern match | 10% | Similarity to user's historical picks (from analyzer.py). Only active when ≥ 10 marked picks exist in history; otherwise this 10% is redistributed equally to technical and fundamental. |

---

## Pages

### Home — Daily Top 10 Picks
- "Run Today's Picks" button triggers the full pipeline on-demand
- Shows last-run timestamp
- "Adjust Weights" button opens a slider panel for live weight tuning (saved back to `config.yaml`)
- Market conditions banner (green = favorable, red = paused)
- Picks table: rank, ticker, company, price, composite score, technical sub-score, fundamental sub-score, primary catalyst tag
- Click any row → expands pick card showing:
  - **"Why Buy Today"** — plain-English narrative assembled from all sources, citing each data point's origin
  - Catalyst tags (color-coded: earnings beat, analyst upgrade, breakout, etc.)
  - Technical signal breakdown (RSI, MACD, SMA, volume)
  - Fundamental snapshot (EPS growth, revenue growth, P/E, analyst rating, profit margin)
  - Market condition indicators at time of pick
  - 30-day price chart (Plotly candlestick)
  - "Mark as Picked" button — marks this generated pick as one the user actually acted on (used by pattern learning). All top-10 picks are auto-saved to the DB on each run regardless; this flag is separate.

### History — Past Picks Log
- Table of all auto-saved generated picks: date, ticker, score, catalyst, price at pick
- "Marked as Picked" column — shows which picks the user actually acted on
- Filter by date range, ticker, catalyst type, marked-only
- Sortable columns
- Visual indicator of pattern analysis status ("Used in learning: Yes/No")

### Settings
- Live sliders for all scoring weights (auto-saves to `config.yaml`)
- Toggle each signal on/off
- Configure thresholds (VIX ceiling, volume multiplier, earnings beat %, etc.)
- API key entry fields (Tier B sources)
- Universe configuration (add extra tickers beyond S&P 500 + NDX 100)

---

## Persistence (SQLite Schema)

```sql
picks (
  id INTEGER PRIMARY KEY,
  date TEXT,           -- YYYY-MM-DD
  ticker TEXT,
  company TEXT,
  price REAL,
  composite_score REAL,
  technical_score REAL,
  fundamental_score REAL,
  catalyst_score REAL,
  pattern_score REAL,
  catalysts TEXT,      -- JSON array of catalyst tags
  narrative TEXT,      -- "Why Buy Today" full text
  signals TEXT         -- JSON blob of all signal values
)

market_conditions (
  date TEXT PRIMARY KEY,
  vix REAL,
  spy_vs_50sma REAL,
  fear_greed INTEGER,
  market_favorable INTEGER  -- 0 or 1
)
```

---

## Pattern Analysis (analyzer.py)

Runs separately from the daily pipeline (can be triggered from the Settings page). Compares the feature distributions of stored historical picks against the full stock universe to identify which signals correlated most strongly with the user's selections. Outputs adjusted signal weights that are written back to `config.yaml` under a `[learned]` section, visible and editable.

---

## Configuration (config.yaml)

Every parameter the user might want to change lives here. No magic numbers in code.

```yaml
universe:
  include_sp500: true
  include_ndx100: true
  extra_tickers: []           # add any extra tickers

quality_filter:
  min_market_cap_b: 10        # billion USD
  min_avg_volume: 1_000_000
  require_profitable: true

market_conditions:
  max_vix: 25
  require_above_50sma: true
  min_fear_greed: 30          # 0–100 scale

catalysts:
  earnings_beat:
    enabled: true
    min_beat_pct: 5
    lookback_days: 3
  analyst_upgrade:
    enabled: true
    lookback_days: 3
  volume_breakout:
    enabled: true
    multiplier: 2.0
  high_52w_breakout:
    enabled: true
  guidance_raised:
    enabled: true
  price_target_increase:
    enabled: true
    min_increase_pct: 10

technical_gates:
  rsi_min: 40
  rsi_max: 70
  require_above_20sma: true
  require_macd_bullish: true
  max_extension_pct: 15

scoring:
  technical_weight: 0.35
  fundamental_weight: 0.35
  catalyst_weight: 0.20
  pattern_weight: 0.10
  top_n: 10

signals:
  rsi:           {enabled: true, weight: 1.0}
  macd:          {enabled: true, weight: 1.0}
  momentum_20d:  {enabled: true, weight: 1.0}
  volume_ratio:  {enabled: true, weight: 1.0}
  sma_crossover: {enabled: true, weight: 1.0}
  eps_growth:    {enabled: true, weight: 1.0}
  revenue_growth:{enabled: true, weight: 1.0}
  pe_vs_sector:  {enabled: true, weight: 1.0}
  analyst_consensus: {enabled: true, weight: 1.0}
  profit_margin: {enabled: true, weight: 1.0}

api_keys:         # all optional — Tier A works without these
  alpha_vantage: ""
  benzinga: ""
  newsapi: ""

output:
  db_path: db/stocks.db
  export_csv: true           # also save picks to CSV each day
```

---

## Extensibility

- **Add a new signal:** implement a function in `scorer.py` returning a 0–1 float, add one entry to `config.yaml` under `signals`. The scorer auto-discovers it.
- **Add a new catalyst type:** add a function in `pipeline.py` returning a catalyst dict, add one entry under `catalysts` in config. Gate 3 auto-includes it.
- **Add a new data source:** create a fetcher module in `engine/`, call it from `fetcher.py`. The rest of the pipeline is unaffected.
- **Adjust anything:** edit `config.yaml` or use the Settings page — changes apply on next run. No code changes required for tuning.

---

## Error Handling

- **yfinance rate limit / timeout:** retry with exponential backoff (3 attempts), skip ticker after 3 failures, log warning
- **Finviz scrape fails:** fall back to yfinance news only, log warning
- **RSS feed unreachable:** skip that feed silently, continue with others
- **Tier B API error (bad key, quota exceeded):** skip source silently, build narrative from remaining sources
- **Market data stale (weekend/holiday):** detect and display "Markets closed — showing last available data"
- **No stocks pass gates:** display informative message ("No picks today — market conditions unfavorable" or "No catalyst-driven opportunities found")

---

## Testing

- **Unit tests** (`tests/`) for each engine module: scorer, fetcher (mocked), pipeline gates, analyzer, database CRUD
- **Integration test:** run full pipeline against a small fixed ticker list with mocked yfinance responses
- **Config validation test:** assert all config keys are present and within valid ranges on load
- **No live network calls in tests** — all external data mocked via `pytest-mock` / fixture files

---

## Dependencies

```
dash>=2.14
plotly>=5.18
pandas>=2.1
yfinance>=0.2.36
finviz>=1.4
feedparser>=6.0
requests>=2.31
beautifulsoup4>=4.12
PyYAML>=6.0
pytest>=8.0
pytest-mock>=3.12
```

---

## Out of Scope

- Real-time / auto-refreshing data (on-demand only)
- Push notifications or email alerts
- Brokerage integration or trade execution
- Portfolio tracking or P&L calculation
- Mobile app or PWA
