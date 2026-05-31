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
