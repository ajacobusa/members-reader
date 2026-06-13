"""Per-listing conversion dashboard with diagnostics: high views + low
conversion = LISTING problem; high conversion + low traffic = SEO problem."""
from unittest.mock import patch


def _ctx(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    import quoteforge.config as cfg
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(cfg, "OUTPUT_DIR", tmp_path)
    db.init_db()
    return db


def test_listing_problem_high_views_low_conversion(tmp_path, monkeypatch):
    db = _ctx(tmp_path, monkeypatch)
    from quoteforge.analytics.launch_dashboard import (record_listing_stats,
                                                       listing_conversion)
    record_listing_stats("Birthday Print", 800, 30)   # lots of views
    # only 1 order -> ~0.1% conversion -> listing problem
    db.create_order({"order_id": "O1", "recipient_name": "A", "occasion": "B",
                     "listing": "Birthday Print", "sale_price": 18.99,
                     "gelato_cost": 4.5})
    db.update_order("O1", status="delivered")
    rows = {r["listing"]: r for r in listing_conversion()}
    assert rows["Birthday Print"]["flag"] == "listing_problem"


def test_seo_problem_high_conversion_low_traffic(tmp_path, monkeypatch):
    db = _ctx(tmp_path, monkeypatch)
    from quoteforge.analytics.launch_dashboard import (record_listing_stats,
                                                       listing_conversion)
    record_listing_stats("Wedding Print", 20, 8)      # tiny traffic
    for i in range(3):                                 # 3 orders / 20 views = 15%
        db.create_order({"order_id": f"W{i}", "recipient_name": "A",
                         "occasion": "Wedding", "listing": "Wedding Print",
                         "sale_price": 45.99, "gelato_cost": 6.0})
        db.update_order(f"W{i}", status="delivered")
    rows = {r["listing"]: r for r in listing_conversion()}
    assert rows["Wedding Print"]["flag"] == "seo_problem"


def test_dashboard_text_includes_per_listing_flags(tmp_path, monkeypatch):
    db = _ctx(tmp_path, monkeypatch)
    from quoteforge.analytics.launch_dashboard import (record_listing_stats,
                                                       launch_metrics,
                                                       format_dashboard)
    record_listing_stats("Birthday Print", 800, 30)
    db.create_order({"order_id": "O1", "recipient_name": "A", "occasion": "B",
                     "listing": "Birthday Print", "sale_price": 18.99})
    db.update_order("O1", status="delivered")
    out = format_dashboard(launch_metrics())
    assert "Per-listing" in out or "listing_problem" in out
