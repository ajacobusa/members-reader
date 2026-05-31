from stock_dashboard.engine.sources import newsapi


def test_no_key_returns_empty():
    assert newsapi.fetch_headlines("AAPL", "Apple", "") == []


def test_parses_titles():
    fake = lambda url, params=None, headers=None, timeout=8: {
        "status": "ok", "articles": [{"title": "Apple soars"}, {"title": "Apple beats"}]}
    out = newsapi.fetch_headlines("AAPL", "Apple", "KEY", get_fn=fake)
    assert out == ["Apple soars", "Apple beats"]


def test_bad_payload_returns_empty():
    fake = lambda *a, **k: {"status": "error"}
    assert newsapi.fetch_headlines("AAPL", "Apple", "KEY", get_fn=fake) == []
