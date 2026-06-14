"""The POC end-to-end validation harness runs the real code against an isolated
seeded DB and returns a clean GO verdict — so the POC itself is CI-covered, and
any regression that breaks the workflow turns the POC red here too."""


def test_poc_validation_is_go(tmp_path):
    from quoteforge.poc.harness import run_validation
    r = run_validation(tmp_path / "poc.db", tmp_path)
    m = r["metrics"]
    assert r["go"] is True, [c for c in r["checks"] if not c["ok"]]
    assert m["critical_fail"] == 0 and m["high_fail"] == 0
    assert m["scenarios_passed"] == m["scenarios_total"] == 15
    assert m["coverage_pct"] == 100.0


def test_poc_validation_isolates_global_db(tmp_path):
    """Running the harness must restore the global DB_PATH / TEST_MODE it borrows
    (so it never disturbs the rest of the suite)."""
    import quoteforge.db.database as db
    import quoteforge.config as cfg
    before = (db.DB_PATH, cfg.TEST_MODE, cfg.TRACKING_API_KEY)
    from quoteforge.poc.harness import run_validation
    run_validation(tmp_path / "poc.db", tmp_path)
    assert (db.DB_PATH, cfg.TEST_MODE, cfg.TRACKING_API_KEY) == before


def test_poc_site_is_labelled_test_only(tmp_path):
    from quoteforge.poc.report import build_poc_site
    src = tmp_path / "src.html"
    src.write_text("<html><head><title>Real Store</title></head>"
                   "<body><h1>Shop</h1></body></html>", encoding="utf-8")
    out = build_poc_site(src, tmp_path / "poc.html")
    h = out.read_text(encoding="utf-8")
    assert "<title>POC site — TEST ONLY</title>" in h
    assert "TEST ENVIRONMENT" in h
    assert "<title>Real Store</title>" not in h    # retitled, not the live name


def test_poc_dashboard_renders_verdict(tmp_path):
    from quoteforge.poc.harness import run_validation
    from quoteforge.poc.report import build_dashboard
    r = run_validation(tmp_path / "poc.db", tmp_path)
    out = build_dashboard(r, tmp_path / "dash.html", "2026-01-01")
    h = out.read_text(encoding="utf-8")
    assert "POC" in h and ("GO" in h or "NO-GO" in h)
    assert "Required test scenarios" in h
