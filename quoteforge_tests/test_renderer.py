from unittest.mock import patch, MagicMock
from quoteforge.images.renderer import render_poster

def test_render_poster_returns_url():
    expected_url = "https://cdn.bannerbear.com/output/abc.png"
    create_resp = MagicMock()
    create_resp.json.return_value = {"uid": "test-uid-123", "status": "pending"}
    create_resp.raise_for_status = lambda: None
    poll_resp = MagicMock()
    poll_resp.json.return_value = {"status": "done", "image_url": expected_url}
    poll_resp.raise_for_status = lambda: None

    with patch("quoteforge.images.renderer.requests.post", return_value=create_resp), \
         patch("quoteforge.images.renderer.requests.get", return_value=poll_resp), \
         patch("quoteforge.images.renderer.time.sleep"):
        url = render_poster(
            template_uid="tmpl_abc",
            quote="Rise above the storm.",
            background_url="https://images.unsplash.com/photo-abc",
        )
    assert url == expected_url
