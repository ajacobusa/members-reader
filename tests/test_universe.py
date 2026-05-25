from stock_dashboard.engine.universe import get_universe
from stock_dashboard.engine.config_loader import load_config

def test_universe_returns_list_of_strings(config_path):
    cfg = load_config(config_path)
    tickers = get_universe(cfg)
    assert isinstance(tickers, list)
    assert all(isinstance(t, str) for t in tickers)

def test_universe_contains_known_sp500_tickers(config_path):
    cfg = load_config(config_path)
    tickers = get_universe(cfg)
    assert "AAPL" in tickers
    assert "MSFT" in tickers

def test_universe_contains_known_ndx100_tickers(config_path):
    cfg = load_config(config_path)
    tickers = get_universe(cfg)
    assert "NVDA" in tickers
    assert "META" in tickers

def test_extra_tickers_included(config_path):
    import yaml
    data = yaml.safe_load(config_path.read_text())
    data["universe"]["extra_tickers"] = ["BRK-A"]
    config_path.write_text(yaml.dump(data))
    cfg = load_config(config_path)
    tickers = get_universe(cfg)
    assert "BRK-A" in tickers

def test_universe_deduplicates(config_path):
    cfg = load_config(config_path)
    tickers = get_universe(cfg)
    assert len(tickers) == len(set(tickers))
