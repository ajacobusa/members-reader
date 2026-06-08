"""Customer Preference Graph + Customer Journey Analysis (real data only)."""
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from quoteforge.db import database
    monkeypatch.setattr(database, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "quoteforge.db")
    database.init_db()
    return database


# ── preference graph ──

def test_preferences_empty(fresh_db):
    from quoteforge.analytics.preference_graph import build_graph, format_graph_text
    g = build_graph(min_support=2)
    assert g["insights"] == []
    assert "Not enough order history" in format_graph_text()


def test_distribution_top_choice(fresh_db):
    db = fresh_db
    for _ in range(3):
        db.create_order({"order_id": db.create_order.__name__ + str(_),
                         "occasion": "Anniversary", "material": "Walnut",
                         "sale_price": 50})
    db.create_order({"order_id": "x9", "occasion": "Anniversary",
                     "material": "Oak", "sale_price": 50})
    from quoteforge.analytics.preference_graph import distribution, preferred_for
    rows = distribution("occasion", "material", min_support=1)
    anniv = next(r for r in rows if r["context"] == "Anniversary")
    assert anniv["top_choice"] == "Walnut" and anniv["top_pct"] == 75.0
    pref = preferred_for(occasion="anniversary", choice_field="material")
    assert pref["choice"] == "Walnut" and pref["basis"] == "occasion"


def test_distribution_rejects_bad_field(fresh_db):
    from quoteforge.analytics.preference_graph import distribution
    with pytest.raises(ValueError):
        distribution("occasion", "not_a_signal")


def test_preferred_for_none_without_data(fresh_db):
    from quoteforge.analytics.preference_graph import preferred_for
    assert preferred_for(occasion="Birthday") is None


# ── journey analysis ──

def test_journey_empty(fresh_db):
    from quoteforge.automation.journey_analysis import journey_summary, format_journey_text
    s = journey_summary()
    assert s["funnel"]["started_open"] == 0 and s["funnel"]["converted"] == 0
    assert "Customer Journey Analysis" in format_journey_text()


def test_journey_abandon_rate(fresh_db):
    db = fresh_db
    db.save_customization("a@b.com", listing="Vows", wording="hi", has_photo=True)
    db.save_customization("c@d.com", listing="Vows", wording="yo")
    db.create_order({"order_id": "O1", "sale_price": 50.0})  # one conversion
    from quoteforge.automation.journey_analysis import journey_summary
    f = journey_summary()["funnel"]
    assert f["started_open"] == 2 and f["converted"] == 1
    assert f["abandon_rate_pct"] == round(2 / 3 * 100, 1)
    assert f["top_abandoned_listings"][0][0] == "Vows"


def test_preferences_journey_commands_registered():
    from quoteforge.admin import COMMANDS
    assert "preferences" in COMMANDS and "journey" in COMMANDS
