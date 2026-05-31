import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


def fetch_many(tickers: list[str], fetch_fn: Callable[[str], Optional[Any]],
               max_workers: int = 12) -> dict[str, Any]:
    """Run fetch_fn over tickers concurrently. Failures/None are skipped, never fatal."""
    results: dict[str, Any] = {}
    workers = max(1, min(max_workers, len(tickers) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_fn, t): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                value = fut.result()
            except Exception as exc:  # noqa: BLE001 - isolate per-ticker failures
                log.warning("fetch_many(%s) failed: %s", ticker, exc)
                continue
            if value is not None:
                results[ticker] = value
    return results
