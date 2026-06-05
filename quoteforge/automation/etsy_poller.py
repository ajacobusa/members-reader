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

    data = get_shop_receipts(was_paid=True, was_shipped=False, limit=limit)
    receipts = data.get("results", []) if isinstance(data, dict) else []
    imported, skipped = [], []
    for r in receipts:
        payload = receipt_to_order_payload(r)
        oid = payload.get("etsy_order_id", "")
        if not oid or _is_duplicate(oid):
            skipped.append(oid)
            continue
        try:
            process_webhook_payload(payload)
            imported.append(oid)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to import Etsy receipt {oid}: {exc}")
            skipped.append(oid)
    return {"polled": len(receipts), "imported": imported,
            "skipped": len(skipped), "mock": bool(data.get("mock"))}
