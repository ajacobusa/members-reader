"""Tests for the customer-issue resolution engine + proof-approval audit trail."""
from unittest.mock import patch

from quoteforge.etsy.resolution import (
    resolve_issue, format_resolution_text, ISSUE_CASES,
)
from quoteforge import admin


# ── Decision correctness (the 8 cases + cancellation) ────────────

def test_all_eight_cases_plus_cancellation_present():
    for k in ["changed_mind", "wrong_personalization", "approved_then_changed_mind",
              "damaged_package", "printing_error", "poor_quality", "lost_package",
              "wrong_address", "cancellation"]:
        assert k in ISSUE_CASES


def test_customer_fault_cases_get_no_free_replacement():
    for k in ["changed_mind", "wrong_personalization",
              "approved_then_changed_mind", "wrong_address"]:
        r = resolve_issue(k)
        assert r["fault"] == "customer"
        assert r["gelato_covered"] is False
        assert "No refund" in r["decision"] or "No refund" in r["decision"]


def test_defect_and_damage_get_free_replacement():
    for k in ["damaged_package", "printing_error", "poor_quality"]:
        r = resolve_issue(k)
        assert r["gelato_covered"] is True
        assert "replacement" in r["decision"].lower()
        assert r["customer_pays"] is False


def test_wrong_address_customer_pays():
    r = resolve_issue("wrong_address")
    assert r["customer_pays"] is True
    assert r["gelato_covered"] is False


def test_lost_package_is_investigate_then_replace():
    r = resolve_issue("lost_package")
    assert r["gelato_covered"] is True
    assert "investigation" in r["decision"].lower()
    assert "tracking" in " ".join(r["workflow"]).lower()


def test_natural_language_alias():
    assert resolve_issue("the frame is broken")["category"] == "damaged_package"
    assert resolve_issue("I changed my mind")["category"] == "changed_mind"
    assert resolve_issue("wrong name typo")["category"] == "wrong_personalization"


def test_unrecognized_issue():
    r = resolve_issue("banana")
    assert r["recognized"] is False
    assert "changed_mind" in r["options"]


def test_every_case_has_a_customer_message():
    for k in ISSUE_CASES:
        assert len(resolve_issue(k)["message"]) > 40


# ── Proof-approval evidence strengthens customer-fault denials ───

def test_approval_record_attached_as_evidence():
    order = {"proof_approved": 1, "proof_approved_at": "2026-06-04T10:00:00"}
    r = resolve_issue("approved_then_changed_mind", order=order)
    assert "2026-06-04" in r["evidence"]


def test_no_evidence_without_approval():
    r = resolve_issue("changed_mind", order={"proof_approved": 0})
    assert r["evidence"] == ""


# ── Proof approval audit trail (timestamp recorded) ──────────────

def test_customer_approval_records_timestamp(tmp_path):
    import quoteforge.db.database as db
    from quoteforge.automation import customer_proof as cp
    with patch.object(db, "DB_PATH", tmp_path / "t.db"), \
         patch.object(db, "OUTPUT_DIR", tmp_path), \
         patch("quoteforge.automation.pipeline_orchestrator.resume_after_proof_approval",
               return_value={"status": "resumed"}):
        db.init_db()
        db.create_order({"order_id": "P1", "recipient_name": "Emma",
                         "occasion": "Graduation"})
        cp.record_customer_approval("P1")
        order = db.get_order("P1")
    assert order["proof_approved"] == 1
    assert order["proof_approved_at"]  # timestamp on record


# ── CLI ──────────────────────────────────────────────────────────

def test_cli_resolve(capsys):
    rc = admin.main(["resolve", "damaged_package"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Free replacement" in out
    assert "Message to send" in out


def test_cli_resolve_unknown(capsys):
    rc = admin.main(["resolve", "nonsense"])
    assert rc == 2
