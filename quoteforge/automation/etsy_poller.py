"""Etsy order poller — scheduled intake without Make/Zapier.

Every 5-10 minutes: pull paid-but-unprocessed receipts from Etsy, import each new
one into QuoteForge (idempotently), and let the pipeline take over. This removes
the external automation dependency for order intake.

In TEST_MODE (or without credentials) get_shop_receipts returns no rows, so this
is a safe no-op until real Etsy OAuth credentials are configured.
"""
import logging

logger = logging.getLogger("quoteforge.etsy_poller")


def poll_once(limit: int = 25) -> dict:
    """One polling cycle. Returns a summary of imported/skipped receipts."""
    from quoteforge.automation.etsy_api import (
        get_shop_receipts, receipt_to_order_payload,
    )
    from quoteforge.automation.webhook_server import process_webhook_payload, _is_duplicate

    try:
        data = get_shop_receipts(was_paid=True, was_shipped=False, limit=limit)
    except Exception as exc:  # noqa: BLE001 - an API blip must not abort the cycle; the
        # next 10-min run retries and dedup keeps it safe.
        logger.error(f"Etsy receipt fetch failed: {exc}")
        return {"polled": 0, "imported": [], "skipped": 0, "error": str(exc)}
    receipts = data.get("results", []) if isinstance(data, dict) else []
    imported, skipped, failed = [], [], []
    for r in receipts:
        # Isolate each receipt: a single un-convertible/failing receipt must not wedge
        # the rest of the batch.
        oid = ""
        try:
            payload = receipt_to_order_payload(r)
            oid = payload.get("etsy_order_id", "")
            if not oid or _is_duplicate(oid):
                skipped.append(oid)
                continue
            process_webhook_payload(payload)
            imported.append(oid)
        except Exception as exc:  # noqa: BLE001
            # A FAILED import (not a duplicate skip) strands a PAID order with no DB row,
            # so it must be SURFACED, not just logged: report it + capture to Sentry so
            # the poll job can alert the owner (the failure happens before create_order,
            # so no downstream DB monitor can see it).
            logger.error(f"Failed to import Etsy receipt {oid or '?'}: {exc}")
            failed.append(oid or "?")
            try:
                from quoteforge.automation.monitoring import capture
                capture(exc)
            except Exception as mon_exc:  # noqa: BLE001 - the import failure is logged
                logger.debug("monitoring capture failed: %s", mon_exc)
    logger.info("etsy poll: polled=%d imported=%d skipped=%d failed=%d",
                len(receipts), len(imported), len(skipped), len(failed))
    return {"polled": len(receipts), "imported": imported, "skipped": len(skipped),
            "failed": failed, "mock": bool(data.get("mock"))}
