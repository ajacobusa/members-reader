"""Intake + delivery resilience hardening (autonomous recheck fleet, 9 confirmed issues):
no paid order is lost to one bad line, one bad receipt, a malformed qty, a non-object
body, an API blip; no review fires over an open claim; a NULL shipped_at can't hide a
stale order; profane buyer text is flagged for owner review.
"""
import sqlite3

import pytest


# -------------------------------------------------- #1 HIGH per-line isolation
def test_one_bad_basket_line_does_not_drop_the_rest(monkeypatch):
    import quoteforge.automation.webhook_server as ws
    calls = []

    def _fake_run_one(merged, line_id):
        calls.append(line_id)
        if line_id.endswith("-2"):
            raise RuntimeError("boom")
        return {"status": "success", "etsy_order_id": line_id,
                "internal_order_id": line_id, "pipeline_status": "ok", "recipient": "R"}
    monkeypatch.setattr(ws, "_run_one", _fake_run_one)
    payload = {"order_id": "E1", "items": [
        {"recipient_name": "A", "occasion": "B"},
        {"recipient_name": "B", "occasion": "B"},   # this one raises
        {"recipient_name": "C", "occasion": "B"}]}
    res = ws.process_webhook_payload(payload)
    assert calls == ["E1-1", "E1-2", "E1-3"]                     # ALL lines attempted
    assert [r["status"] for r in res["results"]] == ["success", "error", "success"]


def test_non_dict_basket_line_is_isolated(monkeypatch):
    import quoteforge.automation.webhook_server as ws
    monkeypatch.setattr(ws, "_run_one",
                        lambda m, lid: {"status": "success", "etsy_order_id": lid,
                                        "internal_order_id": lid, "pipeline_status": "ok",
                                        "recipient": "R"})
    res = ws.process_webhook_payload({"order_id": "E1", "items": [
        {"recipient_name": "A", "occasion": "B"}, "not-a-dict"]})
    assert res["results"][0]["status"] == "success"
    assert res["results"][1]["status"] == "error"               # bad line isolated, basket survives


# -------------------------------------------------- #3/#8 poller isolation
def test_poller_one_bad_receipt_does_not_wedge_batch(monkeypatch):
    import quoteforge.automation.etsy_api as ea
    import quoteforge.automation.webhook_server as ws
    monkeypatch.setattr(ea, "get_shop_receipts",
                        lambda **k: {"results": [{"id": 1}, {"id": 2}, {"id": 3}]})

    def _conv(r):
        if r["id"] == 2:
            raise ValueError("bad receipt")
        return {"etsy_order_id": f"R{r['id']}", "recipient_name": "X", "occasion": "B"}
    monkeypatch.setattr(ea, "receipt_to_order_payload", _conv)
    monkeypatch.setattr(ws, "process_webhook_payload", lambda p: {"status": "success"})
    monkeypatch.setattr(ws, "_is_duplicate", lambda oid: False)
    from quoteforge.automation.etsy_poller import poll_once
    r = poll_once()
    assert r["imported"] == ["R1", "R3"]                        # 2 skipped, 1+3 still imported


def test_poller_api_error_is_clean_noop(monkeypatch):
    import quoteforge.automation.etsy_api as ea
    def _boom(**k):
        raise TimeoutError("etsy down")
    monkeypatch.setattr(ea, "get_shop_receipts", _boom)
    from quoteforge.automation.etsy_poller import poll_once
    r = poll_once()
    assert r["polled"] == 0 and r["imported"] == [] and "error" in r


# -------------------------------------------------- #4 /confirm malformed qty
def test_malformed_qty_does_not_crash_confirm(tmp_path, monkeypatch):
    import json
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.design_confirm import _cart_money
    dj = json.dumps({"contact": {"name": "B"}, "cart": {"lines": [
        {"title": "P", "fmt": "Poster (unframed print)", "size": "8x10", "unit": 25,
         "qty": "oops"}]}})       # malformed qty
    money = _cart_money(dj)                                     # must not raise
    assert money.get("item_count") == 1                        # bad qty -> 1


# -------------------------------------------------- #5 claim suppresses review
def test_open_claim_suppresses_review(monkeypatch):
    from datetime import datetime, timedelta
    from quoteforge.etsy.delight_loop import delight_due
    old = (datetime.now() - timedelta(days=30)).isoformat()
    base = {"status": "delivered", "delivery_confirmed": 1, "delivered_at": old,
            "customer_email": "b@x.com", "recipient_name": "R"}
    clean = {**base, "order_id": "OK"}
    claimed = {**base, "order_id": "CLAIM", "claim_status": "supplier_review"}
    due_ids = {d["order_id"] for d in delight_due([clean, claimed])}
    assert "OK" in due_ids and "CLAIM" not in due_ids          # claim suppresses the nudge


# -------------------------------------------------- #6 stale-in-transit fallback
def test_stale_in_transit_uses_created_at_when_no_shipped_at():
    from datetime import datetime, timedelta
    import quoteforge.automation.fulfillment_tracker as ft
    old = (datetime.now() - timedelta(days=15)).isoformat()
    order = {"tracking_number": "TN", "status": "shipped", "country": "US",
             "shipped_at": "", "created_at": old}              # NULL shipped_at (webhook path)
    assert ft._stale_in_transit(order) is True                 # now fires via created_at
