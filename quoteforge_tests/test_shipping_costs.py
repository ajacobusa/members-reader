"""Shipping COST model (high-end per-product + 5% margin + multi-item) and the
shipping-rate review agent that flags when a re-verify against Gelato is overdue."""
import quoteforge.etsy.shipping_costs as sc
import quoteforge.automation.shipping_rate_monitor as srm


# ─────────────────────────────────────────── the cost model
def test_first_item_high_end_per_type():
    assert sc.first_item_cost("Framed Poster - Oak") == 25.0    # framed wins over poster
    assert sc.first_item_cost("Classic Ceramic Mug (11oz)") == 14.0
    assert sc.first_item_cost("Canvas (gallery-wrapped)") == 25.0
    assert sc.first_item_cost("Poster (unframed)") == 15.0


def test_unknown_type_defaults_to_high_end():
    assert sc.first_item_cost("mystery gizmo") == 25.0          # never under-charge


def test_tank_top_priced_as_apparel_not_unknown():
    # REGRESSION: 'Tank Top' fell through to the $25 unknown default (over-charged)
    # because the shipping keyword set drifted from the apparel catalog.
    assert sc.first_item_cost("Tank Top") == 14.0
    assert sc.first_item_cost("tank") == 14.0


def test_shipping_cost_adds_5pct_margin():
    assert sc.shipping_cost("poster", 1) == 15.75              # 15 * 1.05
    assert sc.shipping_cost("mug", 1) == 14.70                 # 14 * 1.05
    assert sc.shipping_cost("framed", 1) == 26.25             # 25 * 1.05


def test_multi_item_adds_each_extra_item():
    # poster x2: (15 + 15*0.75) * 1.05
    assert sc.shipping_cost("poster", 2) == 27.56
    assert sc.shipping_cost("poster", 3) > sc.shipping_cost("poster", 2)


def test_express_upcharge_is_the_delta_over_standard():
    # standard poster 15.75 * (1.6 - 1)
    assert sc.express_upcharge("poster", 1) == 9.45


def test_landed_price_adds_shipping_to_item():
    assert sc.landed_price(20.0, "poster", 1) == 35.75           # 20 + 15.75
    assert sc.landed_price(30.0, "Framed - Oak", 1) == 56.25     # 30 + 26.25


def test_table_override_via_env(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "SHIPPING_COST_TABLE_JSON", '{"poster": 99}')
    assert sc.first_item_cost("poster") == 99.0
    assert sc.shipping_cost("poster", 1) == round(99 * 1.05, 2)


# ─────────────────────────────────────────── the review agent
def test_review_is_stale_until_marked(tmp_path, monkeypatch):
    monkeypatch.setattr(srm, "_ledger_path", lambda: tmp_path / "rev.json")
    r = srm.review_shipping_rates()
    assert r["stale"] is True and r["ok"] is False and r["issues"]   # never reviewed
    assert r["summary"]                                              # reports the table
    srm.mark_reviewed()
    r2 = srm.review_shipping_rates()
    assert r2["stale"] is False and r2["ok"] is True and not r2["issues"]


def test_review_goes_stale_after_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(srm, "_ledger_path", lambda: tmp_path / "rev.json")
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "SHIPPING_RATES_REVIEW_DAYS", 30)
    srm.mark_reviewed("2000-01-01")                                  # long ago
    r = srm.review_shipping_rates()
    assert r["stale"] is True and r["days_since"] > 30


def test_command_and_job_wired():
    import quoteforge.admin as admin
    from quoteforge.automation.scheduler import SCHEDULED_JOBS, EXPECTED_TASK_NAMES
    assert "shipping-rate-check" in admin.COMMANDS
    job = next((j for j in SCHEDULED_JOBS if j.admin_args == "shipping-rate-check"), None)
    assert job is not None and job.name in EXPECTED_TASK_NAMES
