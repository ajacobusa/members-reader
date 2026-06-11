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

    started_marker = ROOT / "logs" / "last_run_started.txt"
    try:
        started_marker.write_text(datetime.date.today().isoformat())
    except Exception:
        pass

    from stock_dashboard.engine.config_loader import load_config
    from stock_dashboard.engine.universe import get_universe
    from stock_dashboard.engine.pipeline import run_pipeline
    from stock_dashboard.db.database import Database
    from stock_dashboard.notifier import build_html_email, send_email

    cfg_path = ROOT / "config.yaml"
    cfg = load_config(cfg_path)

    # Rate-limit accommodation: load any persisted provider cooldowns. If every
    # price source is still exhausted, defer now and resume when quota resets.
    guard = _setup_rate_limit(cfg)
    if guard is not None and _all_price_sources_cooling(guard, cfg):
        _defer_run(guard, cfg, reason="all price sources still rate-limited at startup")
        return

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

    # If the run came up empty because every price source got rate-limited mid-run,
    # defer instead of emailing an empty list — and auto-resume when quota resets.
    if guard is not None and not records and _all_price_sources_cooling(guard, cfg):
        _defer_run(guard, cfg, reason="all price sources rate-limited during run")
        return

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
    from stock_dashboard.paper_trading import summarize, summary_line
    paper = summarize(db.get_closed_picks())
    log.info("PAPER-TRADING: %s", summary_line(paper))
    html = build_html_email(records, market_ok, cfg, paper_note=summary_line(paper))
    success = send_email(subject, html, cfg)
    if not success:
        log.warning("Email was not sent (disabled, unconfigured, or failed)")

    # Successful run — clear any pending auto-resume task and same-day counter.
    if guard is not None:
        _clear_resume_state(cfg)

    log.info("=== Daily run complete: %d picks, email_sent=%s ===", len(records), success)


def _setup_rate_limit(cfg):
    """Configure the process-wide quota guard from config. Returns the guard, or
    None if rate-limit accommodation is disabled."""
    rl = getattr(cfg, "rate_limit", {}) or {}
    if not rl.get("enabled", True):
        return None
    from stock_dashboard.engine import ratelimit
    state_path = ROOT / rl.get("state_file", "logs/quota_state.json")
    guard = ratelimit.configure(state_path, rl)
    guard.clear_expired()
    cooling = guard.cooling()
    if cooling:
        log.warning("rate-limit: providers cooling at startup: %s", cooling)
    return guard


def _price_sources(cfg) -> list[str]:
    """Providers that can supply price history, given current config/keys."""
    sources = ["yfinance", "stooq"]
    if (cfg.api_keys or {}).get("fmp"):
        sources.append("fmp")
    return sources


def _all_price_sources_cooling(guard, cfg) -> bool:
    sources = _price_sources(cfg)
    return bool(sources) and all(guard.is_cooling(p) for p in sources)


def _resume_count_path() -> Path:
    return ROOT / "logs" / f"resume_count_{datetime.date.today().isoformat()}.txt"


def _defer_run(guard, cfg, reason: str) -> None:
    """Schedule a one-shot resume when the soonest quota resets, notify, and exit.
    Capped per day so an hourly-limit storm can't schedule endlessly."""
    rl = getattr(cfg, "rate_limit", {}) or {}
    at = guard.next_reset()
    cooling = guard.cooling()
    log.warning("DEFERRING run — %s; cooling=%s; soonest reset=%s",
                reason, cooling, at.isoformat() if at else None)

    if at is None:
        return

    # Per-day resume cap.
    cap = int(rl.get("max_resumes_per_day", 6))
    cpath = _resume_count_path()
    try:
        count = int(cpath.read_text().strip()) if cpath.exists() else 0
    except Exception:  # noqa: BLE001
        count = 0

    scheduled = False
    if rl.get("auto_resume", True) and count < cap:
        from stock_dashboard.resume import schedule_resume
        scheduled = schedule_resume(at, ROOT)
        if scheduled:
            try:
                cpath.write_text(str(count + 1))
            except Exception:  # noqa: BLE001
                pass

    when = at.astimezone().strftime("%I:%M %p on %b %d") if at else "the next run"
    if scheduled:
        body = (f"<p>StockBoard hit a data-provider quota limit and paused.</p>"
                f"<p>It will <b>resume automatically at {when}</b>, when the quota resets.</p>"
                f"<p>Providers cooling: {', '.join(cooling)}</p>")
        subject = "⏳ StockBoard paused — will auto-resume when quota resets"
    else:
        extra = "daily resume cap reached" if count >= cap else "auto-resume disabled"
        body = (f"<p>StockBoard hit a data-provider quota limit ({extra}).</p>"
                f"<p>It will recover on the next scheduled run after {when}.</p>"
                f"<p>Providers cooling: {', '.join(cooling)}</p>")
        subject = "⏳ StockBoard paused — quota limit hit"
    try:
        from stock_dashboard.notifier import send_email
        send_email(subject, body, cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("deferral email failed: %s", exc)


def _clear_resume_state(cfg) -> None:
    """A healthy run cancels any pending one-shot resume and resets the counter."""
    rl = getattr(cfg, "rate_limit", {}) or {}
    if not rl.get("auto_resume", True):
        return
    try:
        from stock_dashboard.resume import cancel_resume
        cancel_resume()
    except Exception as exc:  # noqa: BLE001
        log.warning("cancel_resume failed: %s", exc)
    try:
        cpath = _resume_count_path()
        if cpath.exists():
            cpath.unlink()
    except Exception:  # noqa: BLE001
        pass


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
