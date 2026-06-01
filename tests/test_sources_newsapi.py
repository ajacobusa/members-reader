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


def test_query_restricts_to_financial_domains_and_context():
    captured = {}
    def fake(url, params=None, headers=None, timeout=8):
        captured["url"] = url
        captured["params"] = params
        return {"status": "ok", "articles": []}
    newsapi.fetch_headlines("AAPL", "Apple", "KEY", get_fn=fake)
    p = captured["params"]
    # restricted to financial outlets
    assert "domains" in p and "cnbc.com" in p["domains"] and "reuters.com" in p["domains"]
    # query carries market context (so we don't get lifestyle noise)
    q = p["q"].lower()
    assert "aapl" in q or "apple" in q
    assert any(term in q for term in ("stock", "shares", "earnings", "analyst"))
    # title/description focused + recency sort
    assert p.get("searchIn") in ("title,description", "title")
