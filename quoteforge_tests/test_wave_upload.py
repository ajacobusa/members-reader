"""Wave 'Upload transactions' CSV: captures income + ALL costs (Etsy fees, Gelato
print + shipping, infrastructure), signed, with sales tax excluded (pass-through).
"""
import csv
import sqlite3

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    import quoteforge.db.database as d
    monkeypatch.setattr(d, "DB_PATH", tmp_path / "t.db")
    d.init_db()
    monkeypatch.setattr("quoteforge.config.MONTHLY_FIXED_COSTS", 0.0, raising=False)
    monkeypatch.setattr("quoteforge.config.USE_MAKE_COM", False, raising=False)
    return d


def _order(d, oid, status="shipped", sale=43.20, **extra):
    conn = sqlite3.connect(d.DB_PATH)
    cols = {"order_id": oid, "recipient_name": "R", "occasion": "birthday",
            "status": status, "sale_price": sale, "created_at": "2026-06-12",
            "gelato_cost": 13.0, "tax_collected": 3.20, "shipping_collected": 5.0,
            "etsy_fees_actual": 2.60, **extra}
    conn.execute(f"INSERT INTO orders ({','.join(cols)}) "
                 f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
    conn.commit()
    conn.close()


def test_rows_capture_income_and_all_costs(db):
    _order(db, "E1", shipping_cost=6.25)
    from quoteforge.etsy.wave_upload import wave_rows
    rows = wave_rows("month")
    by = {r["Description"].split(" - order")[0]: r["Amount"] for r in rows}
    # income positive (tax-exclusive product revenue, item+shipping = 40.00)
    assert by["Etsy sale"] == 40.00
    # every cost is a NEGATIVE line
    assert by["Etsy fees"] == -2.60
    assert by["Gelato print"] == -13.00
    assert by["Gelato shipping"] == -6.25
    # sales tax (3.20) is recorded as a PASS-THROUGH pair that nets to $0
    tax = [r for r in rows if r["account"] == "tax"]
    assert len(tax) == 2 and round(sum(t["Amount"] for t in tax), 2) == 0.0


def test_infrastructure_costs_are_captured(db, monkeypatch):
    _order(db, "E1")
    db.record_api_cost(provider="anthropic", model="claude", operation="quote",
                       cost_usd=0.12, order_id="E1")
    from quoteforge.etsy.wave_upload import wave_rows
    rows = wave_rows("month")
    infra = [r for r in rows if r["Description"].startswith("Infrastructure")]
    assert infra and any(r["Amount"] == -0.12 for r in infra)
    assert any("anthropic" in r["Description"] for r in infra)


def test_net_equals_income_minus_all_costs(db):
    _order(db, "E1", shipping_cost=6.25)
    from quoteforge.etsy.wave_upload import wave_summary
    s = wave_summary("month")
    # 40.00 income - (2.60 fees + 13.00 print + 6.25 ship) = 18.15
    assert s["income"] == 40.00
    assert s["expense"] == round(2.60 + 13.00 + 6.25, 2)
    assert s["net"] == 18.15


def test_write_csv_into_wave_folder(db, tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.config.OUTPUT_DIR", str(tmp_path), raising=False)
    _order(db, "E1")
    from quoteforge.etsy.wave_upload import write_wave_csv, WAVE_COLUMNS
    path = write_wave_csv(period="month")
    assert path.parent.name == "wave" and path.exists()
    with path.open() as fh:
        rd = list(csv.reader(fh))
    assert rd[0] == WAVE_COLUMNS
    # signed amounts: at least one positive (income) and one negative (cost)
    amounts = [float(r[2]) for r in rd[1:]]
    assert any(a > 0 for a in amounts) and any(a < 0 for a in amounts)


def test_daily_wave_job_auto_syncs():
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    job = next((j for j in SCHEDULED_JOBS
                if j.name == "QuoteForge Wave Daily Transactions"), None)
    assert job and job.admin_args == "wave-sync today --auto"
