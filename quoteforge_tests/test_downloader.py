from unittest.mock import patch, MagicMock
from pathlib import Path
from quoteforge.images.downloader import download_png

def test_download_saves_file(tmp_path):
    fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    mock_resp = MagicMock()
    mock_resp.content = fake_bytes
    mock_resp.raise_for_status = lambda: None

    with patch("quoteforge.images.downloader.requests.get", return_value=mock_resp):
        out_path = download_png(
            url="https://cdn.bannerbear.com/abc.png",
            output_dir=tmp_path,
            filename="test_poster",
        )
    assert out_path.exists()
    assert out_path.suffix == ".png"
    assert out_path.read_bytes() == fake_bytes
