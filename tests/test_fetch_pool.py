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
