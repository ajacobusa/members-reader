import pytest
from pathlib import Path
from stock_dashboard.engine.config_loader import load_config, Config

def test_load_config_returns_config(config_path):
    cfg = load_config(config_path)
    assert isinstance(cfg, Config)

def test_scoring_weights_sum_to_one(config_path):
    cfg = load_config(config_path)
    total = (cfg.scoring["technical_weight"] + cfg.scoring["fundamental_weight"]
             + cfg.scoring["catalyst_weight"] + cfg.scoring["pattern_weight"])
    assert abs(total - 1.0) < 1e-6

def test_missing_required_key_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("universe:\n  include_sp500: true\n")
    with pytest.raises(KeyError):
        load_config(bad)

def test_extra_tickers_merged(config_path):
    cfg = load_config(config_path)
    assert isinstance(cfg.universe["extra_tickers"], list)

def test_empty_config_file_raises_value_error(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(empty)

def test_profit_engine_config_blocks_present(config_path):
    cfg = load_config(config_path)
    assert "earnings_surprise" in cfg.factor_weights
    assert cfg.sizing["kelly_multiplier"] == 0.5
    assert cfg.probability_filter["min_probability_gain"] == 0.60
    assert cfg.statistics["return_lookback_days"] == 120
    assert cfg.performance["enrich_only_survivors"] is True
    assert cfg.health["min_fetch_success_rate"] == 0.85
    assert cfg.backtest["auto_tune"] is True
