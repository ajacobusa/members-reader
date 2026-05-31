import logging
from typing import Callable, Optional

log = logging.getLogger(__name__)


def record_outcomes(db, price_fn: Callable[[str, str], Optional[float]],
                    as_of_date: str) -> int:
    """For each pick without a recorded outcome, fetch the realized exit price via
    price_fn(ticker, as_of_date) and store the realized % return. Returns count."""
    recorded = 0
    for row in db.get_unrecorded_picks():
        entry = row.get("price")
        if not entry or entry <= 0:
            continue
        try:
            exit_price = price_fn(row["ticker"], as_of_date)
        except Exception as exc:  # noqa: BLE001
            log.warning("outcome price fetch failed for %s: %s", row["ticker"], exc)
            continue
        if exit_price is None or exit_price <= 0:
            continue
        realized = round((exit_price - entry) / entry * 100.0, 4)
        db.record_outcome(row["id"], realized)
        recorded += 1
    return recorded
