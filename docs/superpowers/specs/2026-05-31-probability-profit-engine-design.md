# Probability-Driven Profit Engine — Design Spec

**Date:** 2026-05-31
**Status:** Awaiting user review
**Builds on:** `2026-05-24-stock-dashboard-design.md` (the existing 5-gate StockBoard pipeline)

---

## Overview

An **additive** enhancement layer on top of the existing catalyst-driven StockBoard pipeline. It transforms the system from a *news/score screener* into a *probability-driven, profit-optimized ranking system*. Nothing in the existing 5-gate pipeline is removed — this layer runs **after** a stock clears the existing gates, enriches it with evidence-based statistics, ranks by expected dollar value, sizes by fractional Kelly, and only surfaces high-conviction setups.

**Optimization target:** maximize *realized* daily/overnight profit — explicitly accepting that overnight edge is small and noisy, so the design favors **fewer, higher-conviction, correctly-sized** trades over more picks.

---

## Core Insight

A per-stock "expected return" computed from that stock's **own historical reaction distribution** (e.g., last 8 earnings moves, last N day-after-catalyst moves) is itself a mini-backtest. This yields evidence-based numbers immediately, without first building a full strategy backtester. The full strategy backtest is a *separate* validation tool that tunes the global signal weights.

---

## Goals

- Replace single-number "expected move" with a **probability distribution**: P(gain), expected return, confidence interval, risk/reward.
- Rank picks by **expected value**, not raw score.
- Size positions by **half-Kelly** (capped), to capture growth while surviving variance.
- Add a **profit gate**: only email picks that clear Score / EV / P(gain) / R:R thresholds; otherwise email "no high-conviction setups."
- Add **options-market intelligence** (free via yfinance option chains) where feasible.
- Add **earnings surprise history** and **analyst revision velocity** as predictive signals.
- **Close the loop**: record realized next-day outcomes per pick so probability estimates self-calibrate and the backtest runs on real picks.
- Validate global weights with a **2–5yr strategy backtest** comparing entry/exit timings.
- Be **honest about limitations** (institutional flow, gamma proxy, small samples).

---

## Architecture (Additive)

Three new engine modules + one enrichment step + outcome tracking. The existing
`pipeline.run_pipeline` is extended to call the enrichment step after Gate 4/5.

```
stock_dashboard/engine/
  statistics.py    # per-stock historical outcome stats → ProbabilityProfile
  options.py       # options-market intelligence → OptionsSignal (graceful skip)
  enrichment.py    # orchestrates stats + options + EV + Kelly → EnrichedPick
  backtest.py      # standalone strategy validator (2-5yr, 4 entry/exit timings)
stock_dashboard/
  outcomes.py      # records realized next-day return per saved pick (closed loop)
```

### Data flow

```
existing 5-gate pipeline → surviving stocks
   → enrichment.enrich(stock, cfg):
        statistics.profile(stock)      → ProbabilityProfile
        options.signal(stock)          → OptionsSignal | None
        compute EV, CI, R:R, Kelly
        → EnrichedPick
   → rank by EV_rank = expected_return × P_gain × conviction
   → Gate 6 (probability_filter): drop picks failing thresholds
   → save (with new columns) + email + dashboard

next run (or separate daily step):
   outcomes.record_yesterday()  → fills realized_return for prior picks
```

---

## New Modules

### `engine/statistics.py`

```python
@dataclass
class ProbabilityProfile:
    ticker: str
    # Earnings surprise history
    earnings_beat_rate: Optional[float]        # 0–1 over last N quarters
    earnings_avg_move_pct: Optional[float]
    earnings_median_move_pct: Optional[float]
    earnings_sample_size: int
    # Analyst revision velocity
    eps_revision_30d_pct: Optional[float]      # (now − 30d ago) / |30d ago|
    eps_revision_60d_pct: Optional[float]
    pt_change_30d_pct: Optional[float]
    # Outcome distribution → probabilities
    prob_gain: float                            # 0–1
    avg_gain_pct: float                         # mean of positive outcomes
    avg_loss_pct: float                         # mean magnitude of negative outcomes
    expected_return_pct: float                  # P_up*avg_gain − P_down*avg_loss
    return_std_pct: float
    ci_low_pct: float                           # expected − k*std (k from config)
    ci_high_pct: float                          # expected + k*std
    risk_reward: float                          # avg_gain / avg_loss
    risk_score: float                           # 0–100, higher = riskier (std/skew based)
    kelly_fraction: float                       # full Kelly (sizing applies the fraction)
    sample_size: int
```

- **Move distribution source:** the stock's own daily returns over a configurable lookback (default ~120 trading days), optionally conditioned on "post-catalyst" days. Earnings moves measured as the close-to-next-close (or open, per backtest finding) return around each `earnings_dates` entry.
- **All fields Optional/guarded** — return `None`/neutral on insufficient data; never crash.

### `engine/options.py`

```python
@dataclass
class OptionsSignal:
    ticker: str
    implied_volatility: Optional[float]
    put_call_ratio: Optional[float]            # volume-based
    unusual_call_volume: bool                   # vol >> open interest
    unusual_put_volume: bool
    max_pain: Optional[float]                    # strike minimizing total option value
    gamma_proxy: Optional[float]                 # SIMPLIFIED OI-based proxy (labeled)
    available: bool                              # False → silently skipped
```

- Sourced from `yfinance` `option_chain` on the nearest 1–2 expiries.
- **Graceful degradation:** tickers without listed options set `available=False`; downstream weights renormalize over present signals.
- `gamma_proxy` is explicitly labeled in UI/email as a proxy, not dealer-positioned GEX.

### `engine/enrichment.py`

```python
@dataclass
class EnrichedPick:
    pick: PickRecord            # existing record
    profile: ProbabilityProfile
    options: Optional[OptionsSignal]
    ev_rank: float              # expected_return × prob_gain × conviction
    suggested_size_pct: float   # half-Kelly, capped
    passes_profit_gate: bool

def enrich(stock, score_result, cfg) -> EnrichedPick: ...
def rank_and_filter(enriched: list[EnrichedPick], cfg) -> list[EnrichedPick]: ...
```

- **Factor score** = weighted blend (per `factor_weights`) of the new normalized factors (earnings surprise, revision velocity, options flow, rel-volume, institutional, insider, technical momentum, sector strength), each scaled 0–1; weights renormalize over whichever factors are available.
- **Conviction** = `cfg.enrichment.conviction_blend × factor_score + (1 − blend) × (existing_composite/100)`, default blend 0.5 — so both the proven 5-gate composite and the new factors contribute.
- **Sizing:** `suggested_size_pct = clamp(kelly_fraction × cfg.sizing.kelly_multiplier, 0, cfg.sizing.max_position_pct)`; total across picks capped at `cfg.sizing.max_total_pct`.

### `engine/backtest.py` (standalone CLI)

`python -m stock_dashboard.backtest --years 3`

- Pulls 2–5yr OHLC for the universe.
- Compares four timings, reporting **win-rate / avg-return / Sharpe / max-drawdown** each:
  - A: buy open → sell next open
  - B: buy close → sell next close
  - C: buy close → sell next open
  - D: buy open → sell close
- Optionally evaluates **signal predictiveness** (does high EV_rank correlate with realized next-day return?) to inform weight tuning.
- Writes a report to `logs/backtest_<date>.txt` and a summary CSV. **Does not auto-write weights** — surfaces recommendations for the user to accept in `config.yaml`.

### `outcomes.py` (closed-loop tracking)

- For each saved pick from a prior trading day, fetch the realized return (per the backtest-winning timing) and write it to a new `realized_return_pct` column + `outcome_recorded` flag.
- Enables: (1) calibration reports (predicted P_gain vs. actual hit rate), (2) the backtest/analyzer to learn from real picks.

---

## Configuration additions (`config.yaml`)

# NEW block — does NOT touch the existing `signals` block (the current scorer's
# rsi/macd/etc. weights remain untouched). These weight the enrichment factors
# that feed conviction/EV_rank. All config-driven, no magic numbers.
factor_weights:
  earnings_surprise:   {enabled: true, weight: 0.15}
  analyst_revision:    {enabled: true, weight: 0.15}
  options_flow:        {enabled: true, weight: 0.20}
  relative_volume:     {enabled: true, weight: 0.10}
  institutional:       {enabled: true, weight: 0.10}   # weak on free data (stale 13F)
  insider:             {enabled: true, weight: 0.10}
  technical_momentum:  {enabled: true, weight: 0.10}
  sector_strength:     {enabled: true, weight: 0.10}

statistics:
  return_lookback_days: 120
  earnings_lookback_quarters: 8
  ci_sigma_multiplier: 1.5          # CI = mean ± 1.5σ
  conditioning: "catalyst"          # "all" | "catalyst"

enrichment:
  conviction_blend: 0.5             # weight on new factor_score vs existing composite

sizing:
  kelly_multiplier: 0.5             # half-Kelly
  max_position_pct: 10.0            # cap per pick
  max_total_pct: 100.0              # cap across all picks

probability_filter:                  # Gate 6 — the profit gate
  enabled: true
  min_composite_score: 80
  min_expected_return_pct: 1.0
  min_probability_gain: 0.60
  min_risk_reward: 2.0
  cost_slippage_haircut_pct: 0.3    # subtracted from EV before the gate

backtest:
  years: 3
  preferred_timing: "C"             # set after running backtest; drives outcome timing
```

---

## Persistence (new additive columns on `picks`)

```sql
ALTER TABLE picks ADD COLUMN expected_return_pct REAL;
ALTER TABLE picks ADD COLUMN prob_gain REAL;
ALTER TABLE picks ADD COLUMN ci_low_pct REAL;
ALTER TABLE picks ADD COLUMN ci_high_pct REAL;
ALTER TABLE picks ADD COLUMN risk_reward REAL;
ALTER TABLE picks ADD COLUMN risk_score REAL;
ALTER TABLE picks ADD COLUMN kelly_fraction REAL;
ALTER TABLE picks ADD COLUMN suggested_size_pct REAL;
ALTER TABLE picks ADD COLUMN earnings_beat_rate REAL;
ALTER TABLE picks ADD COLUMN eps_revision_30d_pct REAL;
ALTER TABLE picks ADD COLUMN options_summary TEXT;   -- JSON: iv, p/c, max_pain, unusual flags
ALTER TABLE picks ADD COLUMN realized_return_pct REAL;
ALTER TABLE picks ADD COLUMN outcome_recorded INTEGER DEFAULT 0;
```

Schema init uses additive `ALTER TABLE ... ADD COLUMN` guarded by a column-exists check, so existing databases migrate non-destructively.

---

## Output changes

### Email (per pick)
- **Expected Return** `+1.8%` and **Range** `−4.5% to +7.2%`
- **P(Gain)** `63%`
- **Suggested size** `Half-Kelly: 4.2%`
- **Risk/Reward** and **Risk Score**
- **Earnings edge** `Beat 6/8 · avg +4.2%`
- **Revision velocity** `EPS +12.5% / 30d`
- **Options tells** `P/C 0.6 · unusual calls · max pain $X`
- When nothing clears the profit gate: a single **"No high-conviction setups today"** card.

### Dashboard
- New columns mirroring the above on the Home table.
- Expanded pick card shows the full `ProbabilityProfile` + `OptionsSignal` + a calibration note once outcomes exist.

---

## Honest Limitations (documented in README + UI labels)

1. **Institutional "flow" is not real on free data** — only quarterly 13F holdings with ~45-day lag. Labeled as stale holdings; weighted low; flagged as the first candidate for a paid-feed upgrade.
2. **Gamma exposure is a simplified OI proxy**, not dealer-positioned GEX.
3. **Probability estimates come from small samples** (≈8 earnings, ≈120 days). Confidence intervals are intentionally wide.
4. **Weights are hypotheses until backtested.** The defaults above are starting points; `backtest.py` must run before they are trusted.
5. **This is decision support, not financial advice.** Overnight edge is small; transaction costs and slippage can erase it — hence the cost haircut and the profit gate.

---

## Testing

- `tests/test_statistics.py` — distribution math (EV, CI, Kelly, R:R) on synthetic return series with known answers; guards for insufficient data.
- `tests/test_options.py` — put/call, max pain, unusual-volume logic on mocked option chains; `available=False` path.
- `tests/test_enrichment.py` — EV ranking order, half-Kelly capping, profit-gate pass/fail boundaries.
- `tests/test_backtest.py` — strategy comparison on a tiny fixed OHLC fixture (no live calls).
- `tests/test_outcomes.py` — realized-return recording + idempotency.
- `tests/test_database.py` (extend) — additive-column migration is non-destructive.
- **No live network calls** — all yfinance/option data mocked.

---

## Out of Scope

- Real (non-stale) institutional flow, true dealer GEX (require paid feeds).
- Intraday signals or auto-execution / brokerage integration.
- ML model training beyond the statistical scoring described here.
- Multi-day holds / portfolio P&L accounting beyond per-pick realized-return tracking.

---

## Build Order (for the implementation plan)

1. `statistics.py` + tests (the heart — evidence-based per-pick numbers)
2. DB additive columns + migration (+ extend `test_database.py`)
3. `enrichment.py` (EV rank, Kelly, profit gate) + tests
4. Wire enrichment into `pipeline.run_pipeline` + integration test
5. `options.py` + tests (graceful degradation)
6. Email + dashboard output fields
7. `outcomes.py` closed-loop tracking + tests + daily-runner hook
8. `backtest.py` standalone validator + tests
9. README: limitations, backtest usage, profit-gate tuning
