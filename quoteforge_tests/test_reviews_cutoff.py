"""Tests for reviews engine + order-by cutoff banner."""
from datetime import date


def test_reviews_crud_and_stats(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db()
    assert db.review_stats()["count"] == 0
    db.add_review("Ann", 5, "Beautiful, made me cry!", listing="Daughter Graduation")
    db.add_review("Bob", 4, "Great quality")
    st = db.review_stats()
    assert st["count"] == 2 and st["avg"] == 4.5
    assert db.get_published_reviews()[0]["customer_name"] in ("Ann", "Bob")


def test_reviews_section_empty_without_reviews(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.etsy.listing_preview import _reviews_section
    assert _reviews_section() == ""        # no fabricated reviews


def test_reviews_section_renders_real(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("quoteforge.db.database.OUTPUT_DIR", tmp_path)
    from quoteforge.db import database as db
    db.init_db(); db.add_review("Ann", 5, "Loved it")
    from quoteforge.etsy.listing_preview import _reviews_section
    h = _reviews_section()
    assert "What customers say" in h and "Ann" in h and "verified review" in h


def test_cutoff_computes_order_by():
    from quoteforge.etsy import shipping_cutoff as sc
    # 30 days before Christmas, lead time 9 days -> order-by is in the future, within window
    c = sc.upcoming_cutoff(today=date(2026, 11, 25), within_days=45,
                           production_days=3, shipping_days=6)
    assert c and c["occasion"] == "Christmas"
    assert c["order_by"] == "2026-12-16"      # 25 Dec - 9 days
    assert "Christmas" in sc.banner_text(c)


def test_cutoff_none_when_far():
    from quoteforge.etsy import shipping_cutoff as sc
    # Early January: nearest occasion (Valentine's order-by) may be >45 days out
    c = sc.upcoming_cutoff(today=date(2026, 1, 2), within_days=10)
    assert c is None


def test_new_commands_registered():
    from quoteforge import admin
    for c in ("add-review", "reviews", "order-by"):
        assert c in admin.COMMANDS
