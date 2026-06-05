"""Tests for API cost capture + daily reporting."""
from unittest.mock import patch

from quoteforge.automation import cost_tracker as ct
from quoteforge import admin


def test_anthropic_pricing_math():
    # 1M input @ $1 + 1M output @ $5 = $6 for Haiku.
    assert ct.anthropic_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0
    # Small call.
    assert ct.anthropic_cost("claude-haiku-4-5", 230, 62) == round(
        230/1e6*1 + 62/1e6*5, 6)


def test_unknown_model_defaults_to_haiku():
    assert ct.anthropic_cost("mystery", 1_000_000, 0) == 1.0


def test_record_and_report(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()

        class U:
            input_tokens = 200
            output_tokens = 100
        ct.record_anthropic_usage("claude-haiku-4-5", U(), operation="quote")
        ct.record_anthropic_usage("claude-haiku-4-5", U(), operation="listing")
        rep = ct.cost_report("today")
    assert rep["calls"] == 2
    assert rep["input_tokens"] == 400
    assert rep["output_tokens"] == 200
    assert rep["total_cost"] > 0
    assert "anthropic" in rep["by_provider"]
    assert set(rep["by_operation"]) == {"quote", "listing"}


def test_report_excludes_other_days(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        # Insert a row dated last month directly.
        db.record_api_cost("anthropic", 0.01, operation="old")
        with db._conn() as c:
            c.execute("UPDATE api_costs SET created_at='2026-01-01 09:00:00'")
        rep = ct.cost_report("today")
    assert rep["calls"] == 0  # the old row is outside today


def test_record_never_raises_on_bad_usage():
    # Best-effort: a None usage must not blow up generation.
    assert ct.record_anthropic_usage("claude-haiku-4-5", None) == 0.0


def test_format_text_and_html(tmp_path):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        ct.record_anthropic_usage("claude-haiku-4-5",
                                  type("U", (), {"input_tokens": 100,
                                                 "output_tokens": 50})())
        rep = ct.cost_report("today")
    assert "API COST REPORT" in ct.format_cost_text(rep)
    assert "API Costs" in ct.format_cost_html(rep)


# ── Generator integration ────────────────────────────────────────

def test_generator_records_cost(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.quotes import generator

    class FakeMsg:
        class usage:
            input_tokens = 150
            output_tokens = 80
        content = [type("C", (), {"text": "Be brave."})()]

    class FakeMessages:
        def create(self, **kwargs):
            return FakeMsg()

    class FakeClient:
        messages = FakeMessages()

    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        generator._invoke(FakeClient(), operation="quote_generation",
                          model="claude-haiku-4-5", max_tokens=100,
                          messages=[{"role": "user", "content": "hi"}])
        rows = db.get_api_costs()
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 150
    assert rows[0]["operation"] == "quote_generation"


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_costs(tmp_path, capsys):
    import quoteforge.db.database as db
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path):
        db.init_db()
        rc = admin.main(["costs", "today"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "API COST REPORT" in out
