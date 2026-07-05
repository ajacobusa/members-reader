"""Automated daily UAT orchestrator - self-tests the Gelato->Etsy gates, no human review.

Invariants protected: the run is MODE-AWARE (pre-go-live placeholders are PENDING, not a
failure that alerts), but a MACHINERY/SAFETY regression (missing table/job, unauthorised
calibration flip, registry drift, duplicate UID, too many failed jobs) is a hard FAIL that
blocks + alerts. Every test isolates the DB into tmp_path.
"""
import json

import pytest

from quoteforge.automation import daily_uat as uat


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    monkeypatch.setenv("GELATO_UID_MAP_FILE", str(tmp_path / "uidmap.json"))
    db.init_db()
    return tmp_path


# ── Happy path (pre-go-live) ─────────────────────────────────────

def test_pre_go_live_passes_with_pending_gates(iso_db):
    r = uat.run_daily_uat(send=False)
    assert r["overall"] == "PASS" and r["environment"] == "test"
    by = {s["step"]: s for s in r["steps"]}
    assert by["deployment_health"]["ok"] is True
    assert by["uid_mapping"]["status"] == "PENDING"        # placeholders expected
    assert by["apparel_calibration"]["status"] == "PENDING"
    assert by["unauthorized_calibration_flip"]["ok"] is True
    assert by["registry_drift"]["ok"] is True


def test_report_and_audit_are_persisted(iso_db):
    uat.run_daily_uat(send=False)
    latest = uat.latest_report()
    assert latest and latest["overall"] == "PASS"
    import quoteforge.db.database as db
    with db._conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM sync_audit_log").fetchone()["n"]
        rep = conn.execute("SELECT COUNT(*) AS n FROM daily_uat_report").fetchone()["n"]
    assert n >= 9 and rep == 1                              # one row per step + one report


# ── Machinery / safety FAILs (alert even pre-go-live) ────────────

def test_missing_table_fails_deployment(iso_db, monkeypatch):
    monkeypatch.setattr(uat, "_REQUIRED_TABLES", uat._REQUIRED_TABLES + ("no_such_table",))
    s = uat.validate_deployment_health()
    assert s["ok"] is False and "no_such_table" in s["missing_tables"]


def test_missing_job_fails_deployment(iso_db, monkeypatch):
    monkeypatch.setattr(uat, "_REQUIRED_JOBS", uat._REQUIRED_JOBS + ("no-such-job",))
    s = uat.validate_deployment_health()
    assert s["ok"] is False and "no-such-job" in s["missing_jobs"]


def test_unauthorized_calibration_flip_fails(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", True)
    r = uat.run_daily_uat(send=False)
    by = {s["step"]: s for s in r["steps"]}
    assert by["unauthorized_calibration_flip"]["ok"] is False
    assert by["apparel_calibration"]["ok"] is False
    assert r["overall"] == "FAIL" and "unauthorized_calibration_flip" in r["failures"]


def test_registry_drift_fails(iso_db):
    from quoteforge.automation import gelato_readiness as gr
    gr.map_real_gelato_uid("apparel", "S1", "real_uid_1")   # registry has it, not exported
    s = uat.assert_registry_no_drift()
    assert s["ok"] is False and "S1" in s["detail"]
    # once exported, drift clears
    gr.export_registry_to_uid_map()
    assert uat.assert_registry_no_drift()["ok"] is True


def test_duplicate_uid_fails_even_in_test_mode(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.automation.gelato_sync._uid_map",
                        lambda: {"a": "SHARED_UID", "b": "SHARED_UID"})
    s = uat.assert_uid_mapping()
    assert s["ok"] is False and "SHARED_UID" in s["duplicate_uids"]


def test_failed_jobs_threshold_fails(iso_db):
    import quoteforge.db.database as db
    with db._conn() as conn:
        for i in range(uat._FAILED_JOBS_THRESHOLD + 1):
            conn.execute("INSERT INTO sync_runs (job, ok, detail) VALUES (?,0,'boom')",
                         (f"job{i}",))
    s = uat.assert_failed_jobs_below_threshold()
    assert s["ok"] is False and s["failed"] > uat._FAILED_JOBS_THRESHOLD


def test_image_sync_duplicate_urls_fail(iso_db):
    import quoteforge.db.database as db
    with db._conn() as conn:
        conn.execute("INSERT INTO gelato_product_images (gelato_sku, image_url) "
                     "VALUES ('S1','http://x/dup.png'),('S2','http://x/dup.png')")
    s = uat.assert_image_sync()
    assert s["ok"] is False and "http://x/dup.png" in s["duplicates"]


# ── Alerting: only on failure ────────────────────────────────────

def test_alert_only_on_failure(iso_db, monkeypatch):
    alerts = []
    import quoteforge.admin as admin
    monkeypatch.setattr(admin, "_alert", lambda s, b, what=None: alerts.append(s))
    uat.run_daily_uat(send=True)                            # PASS -> no alert
    assert alerts == []
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", True)  # force FAIL
    uat.run_daily_uat(send=True)
    assert alerts and "Daily UAT" in alerts[0]


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_daily_uat(iso_db, capsys):
    from quoteforge import admin
    rc = admin.main(["daily-uat"])
    out = capsys.readouterr().out
    assert rc == 0 and "Daily Automated UAT Report" in out and "Overall     : PASS" in out


def test_uid_mapping_fails_closed_when_runtime_map_unreadable(iso_db, monkeypatch):
    # REGRESSION: a runtime UID map that RAISES must NOT be read as "clean" in live
    # mode. Before the fix, _duplicate_uid_mappings + validate_no_gel_placeholders
    # swallowed the error to empty -> assert_uid_mapping PASSed on an unverifiable map.
    from quoteforge.automation import gelato_readiness as gr
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.config.GELATO_API_KEY", "k")
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "k")
    # a genuinely mapped registry so g1 is not the thing failing
    monkeypatch.setattr(gr, "gate1_status",
                        lambda: {"ready": True, "families": {"apparel": {"placeholders": 0}}})

    def boom():
        raise RuntimeError("runtime map down")
    monkeypatch.setattr("quoteforge.automation.gelato_sync._uid_map", boom)
    s = uat.assert_uid_mapping()
    assert s["ok"] is False and s["status"] == "FAIL"   # fails closed, not false PASS


def test_infra_check_catches_uid_map_swallow(iso_db, monkeypatch):
    # REGRESSION (decoy): prove the new invariant CATCHES the old swallow. Simulate the
    # pre-fix behaviour (validate_no_gel_placeholders with no runtime_read_ok key) and
    # assert the check goes ok=False.
    from quoteforge.automation import gelato_readiness as gr
    monkeypatch.setattr(gr, "validate_no_gel_placeholders",
                        lambda: {"ok": True, "registry_offenders": [], "runtime_offenders": []})
    from quoteforge.automation.infra_check import check_infrastructure
    got = next(c for c in check_infrastructure()["checks"]
               if c["name"] == "uid_map_unverifiable_fails_closed")
    assert got["ok"] is False


def test_image_classification_ranks():
    rows = [{"id": 1, "image_url": "a", "gelato_sku": "S"},
            {"id": 2, "image_url": "b", "gelato_sku": "S"},
            {"id": 3, "image_url": "c", "gelato_sku": "S"}]
    ranked = uat._classify_images(rows)
    assert [r["type"] for r in ranked] == ["studio", "lifestyle", "mockup"]
