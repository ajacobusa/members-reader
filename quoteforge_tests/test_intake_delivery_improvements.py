"""Intake/delivery improvements (from the recheck fleet's opportunity list):
- bounded pipeline concurrency (a burst can't thrash the single SQLite writer)
- alert the owner when an approved /confirm has no shippable contact (was silent)
- carry the apparel two-sided flag into the thin fulfilment line_items
"""
import json


def test_pipeline_concurrency_is_bounded(monkeypatch):
    import quoteforge.automation.webhook_server as ws
    assert ws._PIPELINE_SEM._value <= 6                # bounded (default 6)
    ran = []
    monkeypatch.setattr(ws, "process_webhook_payload", lambda p: ran.append(1))
    ws._process_in_background({})                       # runs through the semaphore
    assert ran == [1]
    assert ws._PIPELINE_SEM._value <= 6                # released afterwards


def test_confirm_with_no_shipto_alerts_owner(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    import quoteforge.automation.design_confirm as dc
    alerts = []
    monkeypatch.setattr(dc, "_alert_owner",
                        lambda email, summary, contact: alerts.append(summary))
    dj = json.dumps({"contact": {"name": "B"},          # name but NO address
                     "cart": {"subtotal": 25.0, "lines": [
                         {"title": "P", "fmt": "Poster (unframed print)",
                          "size": "8x10", "unit": 25, "qty": 1}]}})
    res = dc.confirm_design("buyer@x.com", design_json=dj)
    assert res["order_id"] == ""                        # no order (no ship-to)
    assert alerts and "NO SHIP-TO" in alerts[0]         # owner alerted (was silent)


def test_apparel_twosided_flag_in_line_items(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    db.init_db()
    from quoteforge.automation.design_confirm import _enrich_lines
    out = _enrich_lines([
        {"title": "Shirt", "fmt": "Tee", "size": "M", "unit": 25, "qty": 1,
         "sides": {"front": True, "back": True}},
        {"title": "Poster", "fmt": "Poster (unframed print)", "size": "8x10",
         "unit": 25, "qty": 1}])
    assert out[0]["twosided"] is True
    assert out[1]["twosided"] is False
