# StockBoard

## Autonomous Operation

The system runs with zero manual intervention via two scheduled tasks.

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

## Data Sources

The system works on **Yahoo Finance (yfinance)** alone with no keys. It gets broader,
more reliable coverage when you add free API keys — these aggregate top financial
outlets (Bloomberg/WSJ/Reuters headlines, analyst data, estimates) legitimately.

| Source | Provides | Free key |
|--------|----------|----------|
| Yahoo Finance (yfinance) | prices, fundamentals, options, earnings — baseline | none |
| CNN Fear & Greed | market sentiment gate | none |
| **Financial Modeling Prep** | price targets, analyst upgrades, earnings surprises, news | financialmodelingprep.com/developer |
| **Finnhub** | recommendation trends, news + sentiment | finnhub.io |
| **NewsAPI** | headlines from 80k+ outlets | newsapi.org |

To enable, paste the keys into `config.yaml` under `api_keys:` (`fmp`, `finnhub`,
`newsapi`). The system **degrades gracefully** — any provider without a key is silently
skipped. To stay within free-tier quotas, these providers are queried **only for stocks
that survive the quality + technical gates** (a few dozen per day), never the full universe.

> Paywalled sites (Bloomberg, WSJ, FT, Morningstar) are **not** scraped — their Terms of
> Service prohibit it. The aggregator APIs above are the legitimate way to access that
> breadth of reporting.
