"""Automated apparel calibration - vision QA + capped, auto-reverting gate.

The safety invariants: a vision model can NEVER be the sole unchecked authority over real
garments. The automated gate opens only with owner consent (AUTO_CALIBRATION_ENABLED) + a
passing QA + under a unit cap + NO recent dispute, is fail-safe to CLOSED on any doubt, and
auto-reverts on the first apparel return/dispute. A failing/absent QA never opens it.
"""
import pytest

from quoteforge.automation import calibration_pipeline as cp


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    db.init_db()
    return tmp_path


def _pass(ev, d, p):
    return {"score": 0.95, "checks": {k: True for k in cp._QA_CHECKS}, "detail": "clean"}


def _fail(ev, d, p):
    return {"score": 0.40, "checks": {"placement": False, "size": True, "alignment": True,
                                      "colour": True, "safe_zone": True}, "detail": "offset"}


# ── Vision QA ────────────────────────────────────────────────────

def test_qa_no_op_without_evidence_or_in_test_mode(iso_db):
    assert cp.grade_test_print([]) == {"skipped": True, "passed": False,
                                       "detail": "no evidence photo provided"}
    # TEST_MODE (default in tests) with no injected grader -> skipped, never auto-passes
    assert cp.grade_test_print(["http://x/p.jpg"])["skipped"] is True


def test_qa_pass_and_fail_and_error_are_graded(iso_db):
    assert cp.grade_test_print(["u"], grader=_pass)["passed"] is True
    assert cp.grade_test_print(["u"], grader=_fail)["passed"] is False   # one check false
    def boom(ev, d, p):
        raise RuntimeError("vision down")
    r = cp.grade_test_print(["u"], grader=boom)
    assert r["passed"] is False and r["score"] == 0.0                    # fail-safe


def test_high_score_but_a_failed_check_does_not_pass(iso_db):
    def hi_but_bad(ev, d, p):
        return {"score": 0.99, "checks": {"placement": True, "size": True, "alignment": True,
                                          "colour": True, "safe_zone": False}}
    assert cp.grade_test_print(["u"], grader=hi_but_bad)["passed"] is False


# ── The gate: consent + rails ────────────────────────────────────

def test_gate_closed_without_consent(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.AUTO_CALIBRATION_ENABLED", True)
    cp.record_vision_calibration("real_uid", {"passed": True, "score": 0.95})
    assert cp.auto_calibration_active() is True
    monkeypatch.setattr("quoteforge.config.AUTO_CALIBRATION_ENABLED", False)
    assert cp.auto_calibration_active() is False        # consent off -> closed


def test_record_only_on_pass_and_rejects_placeholder(iso_db):
    assert cp.record_vision_calibration("real_uid", {"passed": False}) == {}
    assert cp.record_vision_calibration("GEL-SEED", {"passed": True, "score": 0.95}) == {}
    row = cp.record_vision_calibration("real_uid", {"passed": True, "score": 0.95})
    assert row and row["approver"] == cp._VISION_APPROVER and row["status"] == "approved"


def test_gate_reverts_on_dispute(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.AUTO_CALIBRATION_ENABLED", True)
    cp.record_vision_calibration("real_uid", {"passed": True, "score": 0.95})
    assert cp.auto_calibration_active() is True
    # a return/dispute since calibration -> gate closes AND check_auto_revert revokes it
    monkeypatch.setattr(cp, "_apparel_issue_since", lambda ts: "apparel order status=returned")
    assert cp.auto_calibration_active() is False
    out = cp.check_auto_revert()
    assert out["reverted"] == 1 and "returned" in out["reason"]
    # after revert the row is revoked, so even clearing the issue leaves it closed
    monkeypatch.setattr(cp, "_apparel_issue_since", lambda ts: "")
    assert cp.auto_calibration_active() is False


def test_gate_reverts_on_unit_cap(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.AUTO_CALIBRATION_ENABLED", True)
    monkeypatch.setattr("quoteforge.config.CALIBRATION_UNIT_CAP", 5)
    cp.record_vision_calibration("real_uid", {"passed": True, "score": 0.95})
    monkeypatch.setattr(cp, "_apparel_units_since", lambda ts: 5)   # cap reached
    assert cp.auto_calibration_active() is False
    assert cp.check_auto_revert()["reverted"] == 1


def test_gate_fail_safe_to_closed_on_error(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.AUTO_CALIBRATION_ENABLED", True)
    cp.record_vision_calibration("real_uid", {"passed": True, "score": 0.95})
    def boom(ts):
        raise RuntimeError("db down")
    monkeypatch.setattr(cp, "_apparel_issue_since", boom)
    assert cp.auto_calibration_active() is False        # unverifiable -> blocked


# ── End to end ───────────────────────────────────────────────────

def test_process_pass_opens_gate(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.AUTO_CALIBRATION_ENABLED", True)
    r = cp.process_test_print_evidence("real_uid", ["http://x/p.jpg"], grader=_pass)
    assert r["action"] == "auto_calibrated" and r["active"] is True


def test_process_fail_blocks_and_opens_issue(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.AUTO_CALIBRATION_ENABLED", True)
    issues = []
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "enqueue_approval",
                        lambda kind, summary, *a, **k: issues.append((kind, summary)))
    r = cp.process_test_print_evidence("real_uid", ["http://x/p.jpg"], grader=_fail)
    assert r["action"] == "blocked" and r["active"] is False
    assert issues and issues[0][0] == "apparel_calibration_failed"


# ── Router integration (money path) ──────────────────────────────

def _apparel_order(uid="apparel_real_uid_1"):
    # faithful_artwork=True clears the earlier #167 faithful-print gate so the order
    # actually reaches the CALIBRATION gate we are testing here.
    return {"order_id": "A1", "gelato_product_uid": uid, "vendor": "gelato",
            "product_type": "apparel", "faithful_artwork": True}


def test_router_blocks_apparel_when_gate_closed(iso_db, monkeypatch):
    from quoteforge.fulfillment.router import route_order
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", False)
    monkeypatch.setattr(
        "quoteforge.automation.calibration_pipeline.auto_calibration_active", lambda: False)
    r = route_order(_apparel_order(),
                    recipient={"name": "A", "address": "1 St", "city": "X",
                               "postCode": "1", "country": "US"},
                    artwork_url="http://x/a.png")
    assert r["status"] == "manual" and "calibration" in r["detail"].lower()


def test_router_allows_apparel_when_auto_calibration_active(iso_db, monkeypatch):
    # REGRESSION: with the automated gate ACTIVE, apparel is no longer held on the
    # calibration gate (it passes that gate; any later hold is a different reason).
    from quoteforge.fulfillment.router import route_order
    monkeypatch.setattr("quoteforge.config.APPAREL_PRINT_CALIBRATED", False)
    monkeypatch.setattr(
        "quoteforge.automation.calibration_pipeline.auto_calibration_active", lambda: True)
    r = route_order(_apparel_order(),
                    recipient={"name": "A", "address": "1 St", "city": "X",
                               "postCode": "1", "country": "US"},
                    artwork_url="http://x/a.png")
    assert not (r["status"] == "manual" and "calibration" in r["detail"].lower())
