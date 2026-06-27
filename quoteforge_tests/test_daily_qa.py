"""Daily QA agent: the always-on check that every product SKU + price is current and
the order book is healthy. Read-only; runs daily and emails the owner on any issue.
"""
import sqlite3


def test_sku_price_audit_structure_and_floor():
    from quoteforge.automation.daily_qa import sku_price_audit
    a = sku_price_audit()
    assert "families" in a and a["families"]                  # every family reported
    assert isinstance(a["placeholder_uids"], int)
    # build_* price every variation to the floor, so NOTHING is below the sanity floor
    assert a["below_floor"] == []
    # each family reports a real product total
    assert any(f.get("total", 0) > 0 for f in a["families"] if "total" in f)


def test_dashboard_counts(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    conn = sqlite3.connect(db.DB_PATH)
    conn.executemany(
        "INSERT INTO orders (order_id,recipient_name,occasion,status,vendor_order_id,"
        "tracking_number) VALUES (?,?,?,?,?,?)",
        [("A", "R", "B", "delivered", "G1", "TN1"),
         ("C", "R", "B", "error", "", "")])
    conn.commit()
    conn.close()
    from quoteforge.automation.daily_qa import qa_dashboard
    d = qa_dashboard()
    assert d["total_orders"] == 2
    assert d["routed"] == 1 and d["with_tracking"] == 1 and d["delivered"] == 1
    assert d["needs_attention"] >= 1                          # the 'error' order
    assert "sku_audit" in d


def test_run_daily_qa_flags_placeholder_uids(tmp_path, monkeypatch):
    # Pre-go-live every UID is a GEL-* placeholder, so the daily check must flag them
    # (this is exactly the 'map real Gelato UIDs' reminder the owner needs).
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    from quoteforge.automation.daily_qa import run_daily_qa
    r = run_daily_qa(send=False)
    assert "issues" in r and "ok" in r
    assert r["sku_audit"]["placeholder_uids"] > 0            # placeholders surfaced
    assert any("placeholder" in i for i in r["issues"])
