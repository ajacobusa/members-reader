"""UID approval lifecycle - resolver DRAFTS -> validation VERIFIES -> admin APPROVES ->
only then go-live. The safety invariant: an auto-resolved UID can NEVER reach the runtime
map (and therefore real orders / real product images) without an explicit admin approval.
Isolated DB per test.
"""
import pytest

from quoteforge.automation import gelato_readiness as gr


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    monkeypatch.setenv("GELATO_UID_MAP_FILE", str(tmp_path / "uidmap.json"))
    db.init_db()
    return tmp_path


def test_draft_is_not_live_until_approved(iso_db):
    row = gr.draft_uid("apparel", "GEL-A", "real_a", score=0.98, reason="match")
    assert row["status"] == "draft" and row["approved_for_go_live"] == 0
    assert gr.registry_uid_map() == {}                    # draft NOT live
    assert [r["sku"] for r in gr.pending_review()] == ["GEL-A"]


def test_low_confidence_is_needs_review(iso_db):
    row = gr.draft_uid("mug", "GEL-M", "real_m", score=0.80, reason="weak")
    assert row["status"] == "needs_review"                # below 0.95 threshold


def test_verify_then_approve_goes_live(iso_db):
    gr.draft_uid("apparel", "GEL-A", "real_a", score=0.99, reason="m")
    v = gr.verify_uid("GEL-A", checker=lambda uid: True)  # injected Gelato-exists check
    assert v["verified"] is True
    assert gr.registry_uid_map() == {}                    # verified != approved
    gr.approve_uid("GEL-A")
    assert gr.registry_uid_map() == {"GEL-A": "real_a"}   # only now live


def test_verify_false_does_not_promote(iso_db):
    gr.draft_uid("apparel", "GEL-A", "real_a", score=0.99, reason="m")
    v = gr.verify_uid("GEL-A", checker=lambda uid: False)  # API says it does not exist
    assert v["verified"] is False
    assert next(r for r in gr.registry_rows() if r["sku"] == "GEL-A")["status"] == "draft"


def test_reject_blocks_forever(iso_db):
    gr.draft_uid("apparel", "GEL-A", "real_a", score=0.99, reason="m")
    gr.reject_uid("GEL-A")
    assert gr.registry_uid_map() == {}
    assert next(r for r in gr.registry_rows() if r["sku"] == "GEL-A")["status"] == "blocked"


def test_manual_owner_map_is_trusted_and_live(iso_db):
    # the manual owner map is the trusted path -> approved on write, immediately live.
    row = gr.map_real_gelato_uid("apparel", "GEL-A", "real_a")
    assert row["approved_for_go_live"] == 1
    assert gr.registry_uid_map() == {"GEL-A": "real_a"}


def test_export_only_writes_approved(iso_db):
    gr.draft_uid("apparel", "GEL-DRAFT", "uid_draft", score=0.99, reason="m")
    gr.map_real_gelato_uid("apparel", "GEL-MANUAL", "uid_manual")
    import json
    e = gr.export_registry_to_uid_map()
    written = json.loads((iso_db / "uidmap.json").read_text())
    assert "GEL-MANUAL" in written and "GEL-DRAFT" not in written   # draft withheld
    assert e["written"] == 1


def test_cli_gelato_uid_queue_and_transitions(iso_db, capsys):
    from quoteforge import admin
    gr.draft_uid("apparel", "GEL-A", "real_a", score=0.99, reason="m")
    assert admin.main(["gelato-uid", "list"]) == 0
    assert "GEL-A" in capsys.readouterr().out
    assert admin.main(["gelato-uid", "approve", "GEL-A"]) == 0
    assert gr.registry_uid_map() == {"GEL-A": "real_a"}
    assert admin.main(["gelato-uid", "reject", "GEL-A"]) == 0
    assert gr.registry_uid_map() == {}


def test_infra_check_draft_needs_approval(iso_db):
    from quoteforge.automation.infra_check import check_infrastructure
    got = next(c for c in check_infrastructure()["checks"]
               if c["name"] == "resolver_draft_needs_approval_to_go_live")
    assert got["ok"] is True
