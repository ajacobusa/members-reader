import json
import time
from pathlib import Path
from typing import Any, Optional


class Cache:
    """Per-ticker per-kind on-disk JSON cache with a TTL in hours."""

    def __init__(self, cache_dir: str, ttl_hours: float):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600

    def _path(self, ticker: str, kind: str) -> Path:
        safe = ticker.replace("/", "_").replace("\\", "_")
        return self.dir / f"{safe}__{kind}.json"

    def get(self, ticker: str, kind: str) -> Optional[Any]:
        p = self._path(ticker, kind)
        if not p.exists():
            return None
        if (time.time() - p.stat().st_mtime) > self.ttl_seconds:
            return None
        try:
            return json.loads(p.read_text())["value"]
        except (ValueError, KeyError):
            return None

    def set(self, ticker: str, kind: str, value: Any) -> None:
        self._path(ticker, kind).write_text(json.dumps({"value": value}))
