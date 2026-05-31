#!/usr/bin/env python3
"""
Entry point for Windows Task Scheduler.
Runs the full pipeline at 7:30 AM weekdays and sends the daily email.
"""
import datetime
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))

logging.basicConfig(
    filename=ROOT / "logs" / "daily.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def is_trading_day() -> bool:
    try:
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS")
        today = datetime.date.today()
        return cal.is_session(today.isoformat())
    except Exception as exc:
        log.warning("exchange_calendars check failed: %s — assuming trading day", exc)
        return datetime.date.today().weekday() < 5  # Mon–Fri fallback


def main() -> None:
    log.info("=== StockBoard daily run started ===")

    if not is_trading_day():
        log.info("Non-trading day — exiting")
        return

    from stock_dashboard.engine.config_loader import load_config
    from stock_dashboard.engine.universe import get_universe
    from stock_dashboard.engine.pipeline import run_pipeline
    from stock_dashboard.db.database import Database
    from stock_dashboard.notifier import build_html_email, send_email

    cfg_path = ROOT / "config.yaml"
    cfg = load_config(cfg_path)

    db = Database(str(ROOT / cfg.output["db_path"]))
    db.init_schema()

    # Closed loop: record realized returns for prior picks before generating new ones
    from stock_dashboard.outcomes import record_outcomes

    def _last_close(ticker: str, as_of: str):
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="5d")
        return float(h["Close"].iloc[-1]) if not h.empty else None

    try:
        recorded = record_outcomes(db, price_fn=_last_close,
                                   as_of_date=datetime.date.today().isoformat())
        log.info("Recorded outcomes for %d prior picks", recorded)
    except Exception as exc:  # noqa: BLE001
        log.warning("outcome recording failed: %s", exc)

    tickers = get_universe(cfg)
    marked_count = len(db.get_picks(marked_only=True))

    market_data = _fetch_market_data()
    earnings_data = _fetch_earnings_data(
        tickers, lookback_days=cfg.catalysts.get("earnings_beat", {}).get("lookback_days", 5))
    sector_pe_map: dict[str, float] = {}

    records, market_ok = run_pipeline(
        tickers=tickers,
        cfg=cfg,
        market_data=market_data,
        earnings_data=earnings_data,
        sector_pe_map=sector_pe_map,
        marked_picks_count=marked_count,
    )

    # Per-pick sanity gate + health report (100% daily error checking)
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
    if is_degraded(report, cfg) and cfg.health.get("abort_if_no_market_data") and not report.market_data_ok:
        send_email("⚠ StockBoard — DEGRADED run (no market data)",
                   f"<p>Run degraded. {report.summary()}</p>", cfg)
        log.warning("Degraded run — withholding picks email")
        return

    db.save_market_conditions(
        date=datetime.date.today().isoformat(),
        vix=market_data.get("vix", 0.0),
        spy_vs_50sma=market_data.get("spy_vs_50sma", 0.0),
        fear_greed=market_data.get("fear_greed", 50),
        market_favorable=market_ok,
    )

    if records:
        db.save_picks(records)
        log.info("Saved %d picks to database", len(records))

        if cfg.output.get("export_csv"):
            import pandas as pd
            import json
            today = datetime.date.today().isoformat()
            csv_path = ROOT / "logs" / f"picks_{today}.csv"
            rows = [
                {**r.__dict__,
                 "catalysts": json.dumps(r.catalysts),
                 "signals": json.dumps(r.signals)}
                for r in records
            ]
            pd.DataFrame(rows).to_csv(csv_path, index=False)
            log.info("CSV exported to %s", csv_path)

    today_str = datetime.date.today().strftime("%A, %B %d %Y")
    subject = f"📈 StockBoard — Top 10 Picks for {today_str}"
    html = build_html_email(records, market_ok, cfg)
    success = send_email(subject, html, cfg)
    if not success:
        log.warning("Email was not sent (disabled, unconfigured, or failed)")

    log.info("=== Daily run complete: %d picks, email_sent=%s ===", len(records), success)


def _fetch_market_data() -> dict:
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]
        spy = yf.Ticker("SPY").history(period="3mo")
        spy_sma50 = spy["Close"].rolling(50).mean().iloc[-1]
        spy_price = spy["Close"].iloc[-1]
        spy_vs_50sma = (float(spy_price) - float(spy_sma50)) / float(spy_sma50)
        fear_greed = _fetch_fear_greed()
        return {"vix": float(vix), "spy_vs_50sma": spy_vs_50sma,
                "fear_greed": fear_greed}
    except Exception as exc:
        log.warning("_fetch_market_data failed: %s — using safe defaults", exc)
        return {"vix": 20.0, "spy_vs_50sma": 0.02, "fear_greed": 50}


def _fetch_fear_greed() -> int:
    try:
        import requests
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = resp.json()
        return int(data["fear_and_greed"]["score"])
    except Exception:
        return 50


def _fetch_earnings_data(tickers: list[str], lookback_days: int = 5) -> dict:
    """Fetch recent earnings (actual vs estimate) for tickers via yfinance."""
    import yfinance as yf
    from stock_dashboard.engine.earnings import parse_recent_earnings
    today = datetime.date.today()
    earnings: dict = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            parsed = parse_recent_earnings(t.earnings_dates, today, lookback_days)
            if parsed is not None:
                earnings[ticker] = parsed
        except Exception:
            continue
    return earnings


if __name__ == "__main__":
    main()
