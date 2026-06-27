"""Durable fulfillment retry (audit #4 - 'never lose an order'): the scheduled job
re-drives errored, never-submitted orders through the idempotent router, recovers
the transient-outage case, never re-sends an already-submitted or submit_unconfirmed
order, and stops after a per-order retry cap. All network mocked.
"""
import json
import sqlite3


def _mk(db, oid, **over):
    cols = {"order_id": oid, "recipient_name": "R", "occasion": "B",
            "status": "error", "gelato_product_uid": "uid-1",
            "artwork_url": "http://x/a.png",
            "ship_to": json.dumps({"name": "R", "addressLine1": "1 St",
                                   "city": "X", "postCode": "30901", "country": "US"})}
    cols.update(over)
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(f"INSERT INTO orders ({','.join(cols)}) "
                 f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
    conn.commit()
    conn.close()


def _setup(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def test_errored_order_is_recovered(tmp_path, monkeypatch):
    # REGRESSION: an errored, never-submitted order is re-driven and recovered.
    db = _setup(tmp_path, monkeypatch)
    _mk(db, "O1")
    import quoteforge.fulfillment.router as router
    monkeypatch.setattr(router, "route_order",
                        lambda *a, **k: {"status": "submitted", "id": "GLT-7"})
    from quoteforge.automation.fulfillment_retry import retry_failed_fulfillments
    r = retry_failed_fulfillments()
    assert r["recovered"] == ["O1"] and r["retried"] == 1
    o = db.get_order("O1")
    assert o["vendor_order_id"] == "GLT-7" and o["status"] == "in_production"
    assert o["fulfillment_retries"] == 1


def test_already_submitted_order_is_never_redriven(tmp_path, monkeypatch):
    # REGRESSION: an order that already has a vendor id is NOT re-driven (no double-submit).
    db = _setup(tmp_path, monkeypatch)
    _mk(db, "O1", vendor_order_id="GLT-EXISTING")
    import quoteforge.fulfillment.router as router
    calls = {"n": 0}
    monkeypatch.setattr(router, "route_order",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    from quoteforge.automation.fulfillment_retry import retry_failed_fulfillments
    r = retry_failed_fulfillments()
    assert r["retried"] == 0 and calls["n"] == 0


def test_submit_unconfirmed_is_excluded(tmp_path, monkeypatch):
    # REGRESSION: ambiguous (submit_unconfirmed) is NEVER auto-retried (double-charge risk).
    db = _setup(tmp_path, monkeypatch)
    _mk(db, "O1", status="submit_unconfirmed")
    import quoteforge.fulfillment.router as router
    calls = {"n": 0}
    monkeypatch.setattr(router, "route_order",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    from quoteforge.automation.fulfillment_retry import retry_failed_fulfillments
    r = retry_failed_fulfillments()
    assert r["retried"] == 0 and calls["n"] == 0


def test_retry_cap_stops_futile_retries(tmp_path, monkeypatch):
    # REGRESSION: an order at the retry cap is not re-driven again; it is flagged exhausted.
    db = _setup(tmp_path, monkeypatch)
    _mk(db, "O1", fulfillment_retries=5)
    import quoteforge.fulfillment.router as router
    calls = {"n": 0}
    monkeypatch.setattr(router, "route_order",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    from quoteforge.automation.fulfillment_retry import retry_failed_fulfillments
    r = retry_failed_fulfillments()
    assert r["retried"] == 0 and calls["n"] == 0 and r["exhausted"] == ["O1"]


def test_still_failing_increments_and_will_retry_again(tmp_path, monkeypatch):
    # A transient failure that persists this tick increments the counter and stays
    # eligible (until the cap) rather than being lost.
    db = _setup(tmp_path, monkeypatch)
    _mk(db, "O1", fulfillment_retries=1)
    import quoteforge.fulfillment.router as router
    monkeypatch.setattr(router, "route_order",
                        lambda *a, **k: {"status": "error", "detail": "still down"})
    from quoteforge.automation.fulfillment_retry import retry_failed_fulfillments
    r = retry_failed_fulfillments()
    assert r["still_failing"] == ["O1"]
    assert db.get_order("O1")["fulfillment_retries"] == 2   # bumped, still < cap
