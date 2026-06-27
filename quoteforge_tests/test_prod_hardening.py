"""Production-readiness hardening (from the 18-point audit):
- #1  Gelato shipping-address endpoint honors GELATO_API_VERSION (was hardcoded v3)
- #7  Gelato 'on_hold' surfaces as an attention status (was dropped as 'ignored')
- #11 the poll path records shipped/delivered in the per-order pipeline_log
- #8  preflight flags transparency (non-blocking), and its docstring no longer
      claims a safe-margin check it never performed
All network/IO mocked or tmp.
"""
import sqlite3


def test_shipping_address_uses_configured_version(monkeypatch):
    # #1 REGRESSION: the shipping-address PUT must use the same version as create/status.
    import quoteforge.automation.gelato_api as ga
    import quoteforge.config as cfg
    monkeypatch.setattr(ga, "TEST_MODE", False)
    monkeypatch.setattr(ga, "GELATO_API_KEY", "k")
    monkeypatch.setattr(cfg, "GELATO_API_VERSION", "v4")
    seen = {}

    class _R:
        status_code = 200
        content = b""

        def raise_for_status(self):
            pass

        def json(self):
            return {}
    monkeypatch.setattr(ga.requests, "put",
                        lambda url, **k: (seen.__setitem__("url", url), _R())[1])
    ga.update_gelato_shipping_address("GLT-1", {"addressLine1": "1 St", "country": "US"})
    assert "/v4/orders/GLT-1/shipping-address" in seen["url"]


def test_gelato_on_hold_surfaces_for_attention(tmp_path, monkeypatch):
    # #7 REGRESSION: an on_hold callback must set status and appear in needs_attention.
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion) VALUES (?,?,?)",
                 ("O1", "R", "B"))
    conn.commit()
    conn.close()
    from quoteforge.automation.webhook_server import process_gelato_callback
    res = process_gelato_callback({"orderReferenceId": "O1", "status": "on_hold"})
    assert res["status"] == "ok"
    assert db.get_order("O1")["status"] == "on_hold"
    rep = db.daily_order_report()
    assert any(o["order_id"] == "O1" for o in rep["needs_attention"])


def test_poll_path_logs_shipped_and_delivered(tmp_path, monkeypatch):
    # #11 REGRESSION: poll-driven shipped + delivered milestones land in pipeline_log.
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("INSERT INTO orders (order_id,recipient_name,occasion,vendor,"
                 "vendor_order_id,status) VALUES (?,?,?,?,?,?)",
                 ("O1", "R", "B", "gelato", "GLT-1", "in_production"))
    conn.commit()
    conn.close()
    import quoteforge.automation.fulfillment_tracker as ft
    monkeypatch.setattr(ft, "_poll_vendor",
                        lambda o, gid: {"tracking_number": "TN1", "status": "delivered",
                                        "carrier": "UPS"})
    ft.sync_tracking()
    stages = {r["stage"] for r in db.get_pipeline_log("O1")}
    assert "tracking_sync" in stages   # shipped milestone recorded
    assert "delivery" in stages        # delivered milestone recorded


def test_preflight_flags_transparency_non_blocking(tmp_path):
    # #8 REGRESSION: a transparent RGBA is flagged via the (non-blocking) opacity check;
    # a fully-opaque RGBA passes it. "opacity" is never a blocking trigger.
    from PIL import Image
    from quoteforge.images.preflight import run_preflight
    transparent = tmp_path / "t.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 0)).save(transparent)
    r = run_preflight(str(transparent), "")
    op = [c for c in r["checks"] if c["name"] == "opacity"]
    assert op and op[0]["ok"] is False
    opaque = tmp_path / "o.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(opaque)
    r2 = run_preflight(str(opaque), "")
    op2 = [c for c in r2["checks"] if c["name"] == "opacity"]
    assert op2 and op2[0]["ok"] is True
