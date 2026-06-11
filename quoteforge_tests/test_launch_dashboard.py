"""Launch dashboard: KPIs computed from DB + recorded Etsy stats (never faked)."""
from unittest.mock import patch


def test_metrics_and_format(tmp_path, monkeypatch):
    """Metrics compute from the DB; conversion appears once views are recorded."""
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        import quoteforge.config as cfg
        monkeypatch.setattr(cfg, "OUTPUT_DIR", tmp_path)
        from quoteforge.analytics.launch_dashboard import (
            launch_metrics, format_dashboard, record_listing_stats)
        record_listing_stats("Personalized Birthday Gift", 200, 15)
        m = launch_metrics()
        assert m["views"] == 200 and m["favorites"] == 15
        assert m["conversion_pct"] is not None      # views recorded -> computed
        out = format_dashboard(m)
        assert "LAUNCH DASHBOARD" in out and "Conversion" in out
        assert "Revenue" in out and "Top occasions" in out
