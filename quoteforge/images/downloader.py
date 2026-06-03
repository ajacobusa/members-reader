import requests
from pathlib import Path


def download_png(url: str, output_dir: Path, filename: str) -> Path:
    """Download a PNG from URL and save to output_dir/filename.png."""
    output_dir.mkdir(parents=True, exist_ok=True)
    response = requests.get(url)
    response.raise_for_status()
    out_path = output_dir / f"{filename}.png"
    out_path.write_bytes(response.content)
    return out_path
