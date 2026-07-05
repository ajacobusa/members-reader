"""Gelato readiness pipeline - the three go-live gates (registry / probe / calibration).

Every test isolates the DB into tmp_path and never touches real state. The invariant
these protect: a GEL-* placeholder can never be laundered into 'verified' or submitted,
the registry feeds the SINGLE runtime UID map (no drift), and APPAREL_PRINT_CALIBRATED
is only legitimate with an owner physical-print approval on record (hard rule #6).
"""
import json

import pytest

from quoteforge.automation import gelato_readiness as gr


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    """Point the DB + the runtime UID-map file at tmp_path, and init the schema."""
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    monkeypatch.setenv("GELATO_UID_MAP_FILE", str(tmp_path / "uidmap.json"))
    db.init_db()
    return tmp_path


# ── Gate 1: registry ─────────────────────────────────────────────

def test_map_real_uid_rejects_placeholder_and_bad_family(iso_db):
    with pytest.raises(ValueError):
        gr.map_real_gelato_uid("apparel", "S1", "GEL-STILL-SEED")   # placeholder
    with pytest.raises(ValueError):
        gr.map_real_gelato_uid("apparel", "S1", "")                 # empty
    with pytest.raises(ValueError):
        gr.map_real_gelato_uid("socks", "S1", "real_uid")           # unknown family
    with pytest.raises(ValueError):
        gr.map_real_gelato_uid("apparel", "", "real_uid")           # no sku


def test_map_real_uid_upserts_and_is_verified(iso_db):
    row = gr.map_real_gelato_uid("apparel", "GEL-M-TSHIRT-M-WHITE", "uid_real_1", "dashboard")
    assert row["status"] == "verified" and row["product_uid"] == "uid_real_1"
    # upsert: same SKU, corrected UID -> one row, updated value
    gr.map_real_gelato_uid("apparel", "GEL-M-TSHIRT-M-WHITE", "uid_real_2", "catalog")
    rows = gr.registry_rows("apparel")
    assert len(rows) == 1 and rows[0]["product_uid"] == "uid_real_2"
    assert gr.registry_uid_map() == {"GEL-M-TSHIRT-M-WHITE": "uid_real_2"}


def test_export_writes_runtime_map_and_merges(iso_db):
    gr.map_real_gelato_uid("mug", "GEL-MUG-11OZ-WHITE", "mug_uid_1", "dashboard")
    # a pre-existing hand-maintained entry must be preserved
    (iso_db / "uidmap.json").write_text(json.dumps({"HAND-SKU": "hand_uid"}), encoding="utf-8")
    out = gr.export_registry_to_uid_map()
    written = json.loads((iso_db / "uidmap.json").read_text())
    assert out["written"] == 1
    assert written["GEL-MUG-11OZ-WHITE"] == "mug_uid_1"   # registry exported
    assert written["HAND-SKU"] == "hand_uid"              # existing entry kept


def test_validate_detects_placeholder_in_registry(iso_db):
    # A legacy/corrupt GEL-* row (bypassing map_real_gelato_uid) must be caught by the
    # defence-in-depth validator, even though map_real would never store it.
    import quoteforge.db.database as db
    with db._conn() as conn:
        conn.execute("INSERT INTO gelato_uid_registry (sku, product_family, product_uid, "
                     "status) VALUES ('BADSKU','apparel','GEL-LEFTOVER','verified')")
    v = gr.validate_no_gel_placeholders()
    assert v["ok"] is False and "BADSKU" in v["registry_offenders"]
    with pytest.raises(RuntimeError):
        gr.assert_no_gel_placeholders()


def test_validate_ok_when_clean(iso_db):
    gr.map_real_gelato_uid("apparel", "S1", "real_uid_1")
    gr.export_registry_to_uid_map()
    assert gr.validate_no_gel_placeholders()["ok"] is True
    gr.assert_no_gel_placeholders()   # does not raise


def test_gate1_status_shape(iso_db):
    g1 = gr.gate1_status()
    assert set(g1["families"]) == set(gr.FAMILIES)
    # pre-go-live: every family still on placeholders -> not ready
    assert g1["ready"] is False


# ── Gate 2: live probe ───────────────────────────────────────────

def test_infer_image_shape_variants():
    f = gr.infer_image_shape
    assert f({"images": ["http://a/x.png"]}) == "images:list[str]"
    assert f({"images": [{"url": "http://a/x.png"}]}).startswith("images:list[dict:")
    assert f({"previewUrl": "http://a/x.png"}) == "previewUrl:str"
    assert f({"mockups": [{"fileUrl": "u"}]}).startswith("mockups:list[dict:")
    assert f("nope") == "unknown"


def test_live_probe_capture_and_gate2(iso_db):
    pid = gr.record_live_probe("QF-1", "SKU-1", gelato_product_id="gp_1",
                               raw_create_response={"id": "gp_1"})
    assert gr.gate2_status()["ready"] is False   # created, shape not confirmed yet
    row = gr.confirm_image_shape(pid, raw_gelato_product_response={"id": "gp_1"},
                                 raw_etsy_image_response={"images": [{"url": "u"}]})
    assert row["status"] == "image_shape_confirmed"
    assert row["detected_image_shape"].startswith("images:list[dict:")
    g2 = gr.gate2_status()
    assert g2["ready"] is True and g2["probe"]["gelato_product_id"] == "gp_1"


# ── Gate 3: calibration ──────────────────────────────────────────

def test_calibration_requires_owner_and_real_uid(iso_db):
    with pytest.raises(ValueError):
        gr.record_calibration_approval("", "owner:aj")             # no uid
    with pytest.raises(ValueError):
        gr.record_calibration_approval("uid_1", "")                # no approver
    with pytest.raises(ValueError):
        gr.record_calibration_approval("GEL-SEED", "owner:aj")     # placeholder uid


def test_calibration_records_and_flags(iso_db, monkeypatch):
    assert gr.calibration_approved("apparel") is False
    row = gr.record_calibration_approval("uid_real_1", "owner:aj", notes="sharp, colour true")
    assert row["status"] == "approved" and row["approver"] == "owner:aj"
    assert gr.calibration_approved("apparel") is True
    # gate3: flag still off -> not ready, but no illegitimate flip
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", False)
    g3 = gr.gate3_status()
    assert g3["ready"] is False and g3["flag_without_approval"] is False
    # flag on + approval -> ready
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", True)
    assert gr.gate3_status()["ready"] is True


def test_gate3_flags_unbacked_flip(iso_db, monkeypatch):
    # flag ON with NO approval on record is the dangerous state (hard rule #6)
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", True)
    g3 = gr.gate3_status()
    assert g3["ready"] is False and g3["flag_without_approval"] is True


# ── Unified report ───────────────────────────────────────────────

def test_readiness_report_structure(iso_db):
    r = gr.readiness_report()
    assert set(r) >= {"gate1_uid_mapping", "gate2_live_probe", "gate3_calibration",
                      "overall_ready", "live_enabled"}
    assert r["overall_ready"] is False   # pre-go-live


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_status_validate_map_export(iso_db, capsys):
    from quoteforge import admin
    assert admin.main(["gelato-readiness", "status"]) == 1          # not ready
    assert "GELATO GO-LIVE READINESS" in capsys.readouterr().out
    assert admin.main(["gelato-readiness", "validate"]) == 0        # clean map so far
    # reject a placeholder via CLI
    assert admin.main(["gelato-readiness", "map-uid", "apparel", "S1", "GEL-X"]) == 1
    # map a real one, then export
    assert admin.main(["gelato-readiness", "map-uid", "apparel", "S1", "real_uid_9", "dash"]) == 0
    assert admin.main(["gelato-readiness", "export"]) == 0
    assert "real_uid_9" in json.loads((iso_db / "uidmap.json").read_text()).values()


def test_cli_calibrate_approve(iso_db, capsys):
    from quoteforge import admin
    assert admin.main(["gelato-readiness", "calibrate-approve", "uid_real_1", "owner:aj",
                       "colour", "true"]) == 0
    assert gr.calibration_approved("apparel") is True
    # placeholder uid rejected
    assert admin.main(["gelato-readiness", "calibrate-approve", "GEL-X", "owner:aj"]) == 1


# ── Preflight + infra-check integration ──────────────────────────

def test_preflight_calibration_gate_blocks_unbacked_flip(iso_db, monkeypatch):
    from quoteforge.preflight import check_calibration_gate
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", True)
    r = check_calibration_gate()[0]
    assert r.status == "FAIL" and "NO owner approval" in r.detail
    # once approved, it passes
    gr.record_calibration_approval("uid_real_1", "owner:aj")
    assert check_calibration_gate()[0].status == "PASS"


def test_infra_check_calibration_flag_backed_catches_unbacked(iso_db, monkeypatch):
    from quoteforge.automation.infra_check import check_infrastructure
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", True)
    r = check_infrastructure()
    got = next(c for c in r["checks"] if c["name"] == "apparel_calibration_flag_backed")
    assert got["ok"] is False and r["ok"] is False


def test_infra_check_readiness_pipeline_wired(iso_db):
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    got = next(c for c in r["checks"] if c["name"] == "gelato_readiness_pipeline_wired")
    assert got["ok"] is True
