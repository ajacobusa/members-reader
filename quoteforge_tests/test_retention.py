"""Tests for the retention / LTV engine."""
from datetime import datetime
from unittest.mock import patch

from quoteforge.etsy.retention import (
    coupon_for, predict_next_occasions, complete_the_story,
    repeat_gift_outreach, lapsed_customers, retention_digest,
    format_retention_text,
)
from quoteforge import admin


def _order(**kw):
    base = {"order_id": "O", "customer_name": "Jen", "customer_email": "j@x.com",
            "recipient_name": "Emma", "relationship": "Daughter",
            "occasion": "Birthday", "created_at": "2026-04-20 10:00:00",
            "status": "shipped"}
    base.update(kw)
    return base


# ── Coupon tiers ─────────────────────────────────────────────────

def test_coupon_tiers():
    assert coupon_for(1, 10).code == "THANKYOU10"
    assert coupon_for(2, 10).code == "LOYAL12"
    assert coupon_for(3, 10).code == "VIP15"
    assert coupon_for(1, 200).code == "COMEBACK15"   # lapse wins


# ── Next-occasion prediction ─────────────────────────────────────

def test_predicts_christmas_for_everyone():
    occ = predict_next_occasions(_order(), datetime(2026, 4, 1))
    assert any(o["occasion"] == "Christmas" for o in occ)


def test_predicts_mothers_day_for_mom_recipient():
    o = _order(relationship="Mother", occasion="Just Because")
    occ = predict_next_occasions(o, datetime(2026, 4, 1))
    assert any("Mother's Day" in x["occasion"] for x in occ)


def test_predicts_recurring_birthday_next_year():
    occ = predict_next_occasions(_order(), datetime(2026, 5, 1))
    bday = [o for o in occ if o["occasion"] == "Birthday"]
    assert bday and 300 < bday[0]["days_away"] < 400


def test_occasions_sorted_soonest_first():
    occ = predict_next_occasions(_order(), datetime(2026, 4, 1))
    days = [o["days_away"] for o in occ]
    assert days == sorted(days)


# ── Cross-sell ───────────────────────────────────────────────────

def test_cross_sell_excludes_prints_and_quantifies():
    c = complete_the_story(_order(occasion="Graduation"))
    assert all(p["category"] != "print" for p in c["addons"])
    assert c["extra_revenue"] > 0
    assert "Emma" in c["message"]


# ── Repeat-gift outreach ─────────────────────────────────────────

def test_outreach_fires_within_lead_window():
    # 20 days before Christmas -> outreach due.
    orders = [_order(occasion="Christmas")]
    actions = repeat_gift_outreach(orders, datetime(2026, 12, 5), lead_days=28)
    assert actions and actions[0]["occasion"] == "Christmas"
    assert actions[0]["days_away"] <= 28


def test_outreach_tiers_coupon_for_repeat_buyer():
    # Two RECENT orders from same customer -> LOYAL12 (not lapsed).
    orders = [_order(order_id="A", created_at="2026-11-20 10:00:00"),
              _order(order_id="B", created_at="2026-11-25 10:00:00")]
    actions = repeat_gift_outreach(orders, datetime(2026, 12, 5), lead_days=28)
    assert actions and actions[0]["coupon"] == "LOYAL12"


def test_outreach_skips_when_no_occasion_near():
    actions = repeat_gift_outreach([_order()], datetime(2026, 6, 15), lead_days=14)
    assert actions == []


# ── Lapsed ───────────────────────────────────────────────────────

def test_lapsed_detection():
    orders = [_order(created_at="2026-01-01 10:00:00")]
    lapsed = lapsed_customers(orders, datetime(2026, 6, 1), days=120)
    assert lapsed and lapsed[0]["days_since"] >= 120
    assert lapsed[0]["coupon"] == "COMEBACK15"


# ── Digest (DB-backed) ───────────────────────────────────────────

def test_retention_digest_from_db(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        db.create_order({"order_id": "R1", "customer_name": "Jen",
                         "customer_email": "j@x.com", "recipient_name": "Emma",
                         "relationship": "Daughter", "occasion": "Christmas"})
        db.update_order("R1", status="shipped")
        d = retention_digest(datetime(2026, 12, 5))
    assert d["order_count"] == 1
    assert "RETENTION" in format_retention_text(d)


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_retention(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["retention"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "RETENTION & LTV ACTIONS" in out
