"""real-images orchestrator - one command to get GENUINE Gelato product photos onto the
storefront (no scraping). Safe no-op until live; never fabricates an image."""
import pytest

from quoteforge.automation import real_images as ri


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    db.init_db()
    return tmp_path


def test_bootstrap_no_op_and_reports_steps_pre_go_live(iso_db):
    rep = ri.bootstrap(pull=False)
    assert rep["live"] is False and rep["real_images"] == 0
    assert rep["unmapped_skus"] > 0                       # placeholders still need UIDs
    assert rep["pulled"] is None                          # nothing pulled (not live)
    # the exact go-live path is surfaced
    joined = " ".join(rep["next_steps"]).lower()
    assert "gelato-resolve" in joined and "real-images pull" in joined


def test_pull_is_no_op_without_live(iso_db):
    # pull=True must NOT attempt a fetch when not live / no store id
    rep = ri.bootstrap(pull=True)
    assert rep["pulled"] is None                          # no-op, never raised


def test_coverage_read_only(iso_db):
    c = ri.coverage()
    assert set(c) == {"real_images", "unmapped_skus"}
    assert c["real_images"] == 0                          # no real images pre-go-live


def test_format_report_contains_sections(iso_db):
    txt = ri.format_report(ri.bootstrap())
    assert "REAL PRODUCT IMAGES" in txt and "Next:" in txt


def test_cli_real_images(iso_db, capsys):
    from quoteforge import admin
    assert admin.main(["real-images"]) == 0
    out = capsys.readouterr().out
    assert "REAL PRODUCT IMAGES" in out and "real images mapped" in out
