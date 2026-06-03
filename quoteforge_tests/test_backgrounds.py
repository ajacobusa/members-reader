from unittest.mock import patch
from quoteforge.images.backgrounds import fetch_background_url

def test_fetch_returns_url():
    fake_response = {
        "results": [{"urls": {"full": "https://images.unsplash.com/photo-abc"}}]
    }
    with patch("quoteforge.images.backgrounds.UNSPLASH_ACCESS_KEY", "test-key"), \
         patch("quoteforge.images.backgrounds.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_response
        mock_get.return_value.raise_for_status = lambda: None
        url = fetch_background_url("mountain sunrise dramatic")
    assert url.startswith("https://")

def test_fetch_returns_none_on_empty_results():
    fake_response = {"results": []}
    with patch("quoteforge.images.backgrounds.UNSPLASH_ACCESS_KEY", "test-key"), \
         patch("quoteforge.images.backgrounds.requests.get") as mock_get:
        mock_get.return_value.json.return_value = fake_response
        mock_get.return_value.raise_for_status = lambda: None
        url = fetch_background_url("something obscure")
    assert url is None
