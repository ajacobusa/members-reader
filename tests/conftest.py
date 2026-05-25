import csv
import pytest
from pathlib import Path


@pytest.fixture
def config_path(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
universe:
  include_sp500: true
  include_ndx100: true
  extra_tickers: []
quality_filter:
  min_market_cap_b: 10
  min_avg_volume: 1000000
  require_profitable: true
market_conditions:
  max_vix: 25
  require_above_50sma: true
  min_fear_greed: 30
catalysts:
  earnings_beat: {enabled: true, min_beat_pct: 5, lookback_days: 3}
  analyst_upgrade: {enabled: true, lookback_days: 3}
  volume_breakout: {enabled: true, multiplier: 2.0}
  high_52w_breakout: {enabled: true}
  guidance_raised: {enabled: true}
  price_target_increase: {enabled: true, min_increase_pct: 10}
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
  rsi: {enabled: true, weight: 1.0}
  macd: {enabled: true, weight: 1.0}
  momentum_20d: {enabled: true, weight: 1.0}
  volume_ratio: {enabled: true, weight: 1.0}
  sma_crossover: {enabled: true, weight: 1.0}
  eps_growth: {enabled: true, weight: 1.0}
  revenue_growth: {enabled: true, weight: 1.0}
  pe_vs_sector: {enabled: true, weight: 1.0}
  analyst_consensus: {enabled: true, weight: 1.0}
  profit_margin: {enabled: true, weight: 1.0}
api_keys:
  alpha_vantage: ""
  benzinga: ""
  newsapi: ""
email:
  enabled: false
  recipient: test@example.com
  sender: test@example.com
  app_password: ""
  smtp_host: smtp.gmail.com
  smtp_port: 587
schedule:
  time: "07:30"
  days: [MON, TUE, WED, THU, FRI]
  skip_market_holidays: true
output:
  db_path: ":memory:"
  export_csv: false
""")
    return cfg


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """CSV with two members and standard column names."""
    csv_file = tmp_path / "members.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "first_name", "last_name", "email"])
        writer.writeheader()
        writer.writerows([
            {"id": "1", "first_name": "Alice", "last_name": "Smith", "email": "alice@example.com"},
            {"id": "2", "first_name": "Bob", "last_name": "Jones", "email": "bob@example.com"},
        ])
    return csv_file


@pytest.fixture
def alternate_columns_csv(tmp_path: Path) -> Path:
    """CSV using 'firstname'/'lastname' instead of 'first_name'/'last_name'."""
    csv_file = tmp_path / "alt_members.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["firstname", "lastname"])
        writer.writeheader()
        writer.writerows([
            {"firstname": "Carol", "lastname": "White"},
        ])
    return csv_file


@pytest.fixture
def empty_csv(tmp_path: Path) -> Path:
    """CSV with headers but no data rows."""
    csv_file = tmp_path / "empty.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["first_name", "last_name"])
        writer.writeheader()
    return csv_file
