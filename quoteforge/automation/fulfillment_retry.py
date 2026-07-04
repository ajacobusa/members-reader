"""Durable fulfillment retry - the 'never lose an order' backstop.

The pipeline already retries a transient Gelato failure in-process (retry.py, 3
attempts). But if the outage outlasts those few seconds the order is left at
status='error' and only a human re-submits it. This scheduled job re-drives those
errored orders through the SAME idempotent router, so a longer outage self-heals.

Safety:
  - Only orders at status='error' with NO vendor_order_id are eligible. A confirmed
    'error' means the order was NOT submitted (the ambiguous timeout/5xx-after-POST
    case is 'submit_unconfirmed', which is intentionally EXCLUDED - re-sending it
    could double-charge).
  - route_order's own idempotency guard still runs, so even a racing re-drive can
    submit at most once.
  - A per-order retry CAP (fulfillment_retries) and an age cap bound futile retries
    on a permanent failure (e.g. a bad product UID) - it stops after the cap and
    stays surfaced for the owner via order_monitor / the daily report.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

MAX_RETRIES = 5            # stop re-driving a given order after this many attempts
MAX_AGE_HOURS = 72         # don't resurrect a stale order older than this


def _eligible(order: dict, max_retries: int) -> bool:
    """An order is safe to re-drive iff it confirmed-failed to submit, has not
    already submitted, and is under the retry cap."""
    return (
        (order.get("status") or "") == "error"
        and not (order.get("vendor_order_id") or order.get("gelato_order_id"))
        and int(order.get("fulfillment_retries") or 0) < max_retries
    )


def _within_age(order: dict, max_age_hours: int) -> bool:
    """True when the order was created within the age cap (best-effort parse)."""
    from datetime import datetime, timedelta
    ts = (order.get("created_at") or "").strip()
    if not ts:
        return True   # no timestamp -> don't exclude on age
    try:
        created = datetime.fromisoformat(ts.replace("Z", ""))
    except ValueError:
        return True
    return datetime.now() - created <= timedelta(hours=max_age_hours)


def retry_failed_fulfillments(limit: int = 500, max_retries: int = MAX_RETRIES,
                              max_age_hours: int = MAX_AGE_HOURS) -> dict:
    """Re-drive errored, never-submitted orders through the idempotent router.

    Returns a summary: {retried, recovered, still_failing, skipped, exhausted}.
    """
    from quoteforge.db.database import (init_db, get_all_orders, get_order,
                                        update_order)
    from quoteforge.automation.retry import retry_call
    from quoteforge.fulfillment.router import route_order
    init_db()
    recovered, still_failing, exhausted = [], [], []
    retried = 0
    for o in get_all_orders(limit):
        if (o.get("status") or "") == "error" \
                and not (o.get("vendor_order_id") or o.get("gelato_order_id")) \
                and int(o.get("fulfillment_retries") or 0) >= max_retries:
            exhausted.append(o["order_id"])     # capped out - owner must intervene
            continue
        if not _eligible(o, max_retries) or not _within_age(o, max_age_hours):
            continue
        # Need a destination + artwork + product to re-submit; otherwise it isn't a
        # transient-outage case, it's an incomplete order (left for the operator).
        product_uid = o.get("gelato_product_uid") or o.get("product_uid")
        artwork_url = o.get("artwork_url")
        recipient = {}
        try:
            recipient = json.loads(o.get("ship_to") or "{}") or {}
        except (TypeError, ValueError):
            recipient = {}
        if not (product_uid and artwork_url and recipient):
            continue

        retried += 1
        update_order(o["order_id"],
                     fulfillment_retries=int(o.get("fulfillment_retries") or 0) + 1)
        try:
            resp = retry_call(
                route_order,
                {"order_id": o["order_id"], "vendor": o.get("vendor") or "gelato",
                 "gelato_product_uid": product_uid,
                 # product_type MUST reach route_order or the calendar/apparel holds
                 # no-op on this retry path too (route_order reads it only from the dict).
                 "product_type": o.get("product_type") or ""},
                recipient=recipient, artwork_url=artwork_url)
        except Exception as exc:  # noqa: BLE001 - a raise here just means try again next tick
            logger.error("retry-fulfillment %s raised: %s", o["order_id"], exc)
            still_failing.append(o["order_id"])
            continue
        st = resp.get("status")
        if st in ("submitted", "fulfilled", "duplicate"):
            vid = resp.get("id", "")
            if vid:
                update_order(o["order_id"], gelato_order_id=vid,
                             vendor_order_id=vid, status="in_production")
            recovered.append(o["order_id"])
            from quoteforge.db.database import log_pipeline_stage
            log_pipeline_stage(o["order_id"], "gelato_order", "success",
                               f"recovered by retry job: {st} {vid}")
        else:
            still_failing.append(o["order_id"])

    logger.info("retry-fulfillment: retried=%d recovered=%d still_failing=%d "
                "exhausted=%d", retried, len(recovered), len(still_failing),
                len(exhausted))
    return {"retried": retried, "recovered": recovered,
            "still_failing": still_failing, "exhausted": exhausted,
            "skipped": max(0, retried - len(recovered) - len(still_failing))}
