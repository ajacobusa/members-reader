"""The 10 go-live gates: grounded daily verification + owner sign-offs.

REGRESSION suite for quoteforge/automation/golive_gates.py - the gate board
the owner uses to answer "are we clear for production?". Every behavioral gate
here runs the REAL code against throwaway state (temp DB / temp dirs), never
production. Machine-state gates (backup rehearsal, full infra sweep) run in
the daily scheduled job, not here - unit tests must stay hermetic."""
from quoteforge.automation import golive_gates as gg


def test_gate_registry_complete_and_callable():
    # REGRESSION: the board must always carry exactly the 10 agreed gates,
    # each with a callable check - a silently dropped gate is a fake "ready".
    assert len(gg.GATES) == 10
    ids = [g["id"] for g in gg.GATES]
    assert len(set(ids)) == 10
    assert set(ids) == {"payment_webhooks", "order_locking", "proof_hash",
                        "shipping_margin", "apparel_calibration",
                        "backup_restore", "webhook_flood", "chargeback_package",
                        "infra_check_green", "suite_documented"}
    assert all(callable(g["check"]) for g in gg.GATES)
    assert [g["num"] for g in gg.GATES] == list(range(1, 11))


def test_gate2_order_locking_verified_behaviorally():
    # REGRESSION (gate 2): a locked order must reject a design edit with
    # OrderLockedError, allow a same-value no-op, and allow ONLY the audited
    # allow_locked override - proven by running the real DB code on a temp DB.
    ok, detail = gg._gate_order_locking()
    assert ok, detail


def test_gate7_webhook_flood_idempotent():
    # REGRESSION (gate 7): 20x the same order intake must land exactly one row.
    ok, detail = gg._gate_webhook_flood()
    assert ok, detail


def test_gate4_shipping_tripwires_fire():
    # REGRESSION (gate 4): every international lane is modeled and the
    # variance tripwire fires on overrun/undercollection, stays quiet when
    # healthy - the "rate never exceeds quote" detector.
    ok, detail = gg._gate_shipping_margin()
    assert ok, detail


def test_gate3_proof_hash_chain():
    # REGRESSION (gate 3): file_sha256 is a true sha256 and the approval
    # recorder still stores the print-file hash with the consent record.
    ok, detail = gg._gate_proof_hash()
    assert ok, detail


def test_gate1_webhook_edges_safe():
    # REGRESSION (gate 1): HMAC accept/tamper-reject + malformed payloads
    # neither crash nor bypass verification.
    ok, detail = gg._gate_payment_webhooks()
    assert ok, detail


def test_gate8_chargeback_package_assembles(tmp_path, monkeypatch):
    # REGRESSION (gate 8): the dispute-evidence package assembles with every
    # section truthy, and a missing consent record is DETECTED, not papered over.
    monkeypatch.setattr(gg, "SAMPLE_DIR", tmp_path / "golive")
    ok, detail = gg._gate_chargeback_package()
    assert ok, detail
    assert (tmp_path / "golive" / "chargeback_evidence_sample.json").exists()
    incomplete = gg.build_chargeback_package({"order_id": "X"})  # no approval
    assert not incomplete["print_file_sha256"]                   # detectable gap


def test_signoff_roundtrip_and_readiness(tmp_path, monkeypatch):
    # REGRESSION: a gate needing an owner sign-off is NOT ready on a green
    # check alone; recording the sign-off makes it ready; clearing it (e.g.
    # after a regression) takes readiness away again; unknown ids are rejected.
    monkeypatch.setattr(gg, "SIGNOFF_PATH", tmp_path / "signoffs.json")
    fake = [{"num": 1, "id": "order_locking", "owner_signoff": True,
             "title": "t", "check": lambda: (True, "green")},
            {"num": 2, "id": "suite_documented", "owner_signoff": False,
             "title": "t2", "check": lambda: (True, "green")}]
    monkeypatch.setattr(gg, "GATES", fake)
    r = gg.run_gates()
    byid = {g["id"]: g for g in r["gates"]}
    assert byid["order_locking"]["ok"] and not byid["order_locking"]["ready"]
    assert byid["suite_documented"]["ready"]          # no sign-off required
    assert not r["ready"]
    gg.record_signoff("order_locking", note="drill done")
    assert gg.run_gates()["ready"]
    gg.clear_signoff("order_locking")
    assert not gg.run_gates()["ready"]
    try:
        gg.record_signoff("nonsense-gate")
        raise AssertionError("unknown gate id must be rejected")
    except ValueError:
        pass


def test_failed_check_is_never_ready_even_signed_off(tmp_path, monkeypatch):
    # REGRESSION: an owner sign-off must NEVER outrank a failing automated
    # check - a gate that regresses after sign-off goes un-ready (fail closed).
    monkeypatch.setattr(gg, "SIGNOFF_PATH", tmp_path / "signoffs.json")
    fake = [{"num": 1, "id": "order_locking", "owner_signoff": True,
             "title": "t", "check": lambda: (False, "regressed")}]
    monkeypatch.setattr(gg, "GATES", fake)
    gg.record_signoff("order_locking")
    r = gg.run_gates()
    assert not r["gates"][0]["ready"] and not r["ready"]


def test_crashing_check_fails_closed(tmp_path, monkeypatch):
    # REGRESSION: a gate check that CRASHES is a failed gate, never a skipped
    # one - the sweep itself must not raise.
    monkeypatch.setattr(gg, "SIGNOFF_PATH", tmp_path / "signoffs.json")

    def boom():
        raise RuntimeError("kaboom")

    fake = [{"num": 1, "id": "order_locking", "owner_signoff": False,
             "title": "t", "check": boom}]
    monkeypatch.setattr(gg, "GATES", fake)
    r = gg.run_gates()
    assert not r["gates"][0]["ok"] and "crashed" in r["gates"][0]["detail"]


def test_admin_commands_and_daily_job_wired():
    # REGRESSION: the board is reachable (admin golive-gates / golive-signoff)
    # and scheduled daily - EXPECTED_TASK_NAMES derives from SCHEDULED_JOBS so
    # the healthcheck follows automatically.
    from quoteforge.admin import COMMANDS
    assert "golive-gates" in COMMANDS and "golive-signoff" in COMMANDS
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    job = next((j for j in SCHEDULED_JOBS
                if j.name == "QuoteForge Go-Live Gates"), None)
    assert job is not None and "golive-gates" in job.admin_args


def test_automated_gates_carry_no_signoff_burden():
    # REGRESSION: gates whose human step was AUTOMATED (restore drill runs the
    # restored code, HTTP flood, policy cross-check, fresh-clone infra drill)
    # must not keep demanding a sign-off; only the two irreducibly human gates
    # (processor dashboard, physical print) plus evidence-pending proof_hash do.
    byid = {g["id"]: g for g in gg.GATES}
    for auto in ("backup_restore", "webhook_flood", "chargeback_package",
                 "infra_check_green", "order_locking", "shipping_margin",
                 "suite_documented"):
        assert not byid[auto]["owner_signoff"], auto
    for human in ("payment_webhooks", "apparel_calibration", "proof_hash"):
        assert byid[human]["owner_signoff"], human
    assert callable(byid["proof_hash"].get("evidence"))


def test_recorded_evidence_satisfies_a_human_gate(tmp_path, monkeypatch):
    # REGRESSION: recorded automated EVIDENCE (the live proof-hash MATCH)
    # makes a human gate ready without a manual sign-off - and a MISMATCH
    # never does.
    monkeypatch.setattr(gg, "SIGNOFF_PATH", tmp_path / "signoffs.json")
    state = {"ev": False}
    fake = [{"num": 1, "id": "proof_hash", "owner_signoff": True,
             "evidence": lambda: state["ev"],
             "title": "t", "check": lambda: (True, "green")}]
    monkeypatch.setattr(gg, "GATES", fake)
    assert not gg.run_gates()["ready"]          # green but no evidence yet
    state["ev"] = True
    r = gg.run_gates()
    assert r["ready"] and r["gates"][0]["evidenced"]


def test_proofcheck_records_match_and_mismatch(tmp_path, monkeypatch):
    # REGRESSION: record_live_proof_check hashes OUR print file, compares with
    # the fetched hash, and persists honest evidence either way.
    import hashlib as hl
    monkeypatch.setattr(gg, "PROOF_EVIDENCE_PATH",
                        tmp_path / "proof_hash_evidence.json")
    art = tmp_path / "art.jpg"
    art.write_bytes(b"live-print-bytes")
    local = hl.sha256(b"live-print-bytes").hexdigest()
    monkeypatch.setattr("quoteforge.automation.print_quality.hashable_print_file",
                        lambda order: str(art))
    from quoteforge.db import database
    monkeypatch.setattr(database, "get_order",
                        lambda oid: {"order_id": oid})
    ev = gg.record_live_proof_check("QF-TEST-1", local)
    assert ev["match"] and gg._proof_evidence_ok()
    ev2 = gg.record_live_proof_check("QF-TEST-1", "deadbeef" * 8)
    assert not ev2["match"] and not gg._proof_evidence_ok()


def test_gate7_http_flood_single_row():
    # REGRESSION (gate 7, upgraded): 20 CONCURRENT posts through the real
    # Flask stack yield exactly one order row, all 2xx, threads settled.
    ok, detail = gg._gate_webhook_flood()
    assert ok, detail
    assert "HTTP" in detail     # the real stack ran, not the fallback


def test_gate8_package_matches_storefront_copy(tmp_path, monkeypatch):
    # REGRESSION (gate 8, upgraded): the evidence package is cross-checked
    # against the storefront's own consent sentence + 7-day window verbatim.
    monkeypatch.setattr(gg, "SAMPLE_DIR", tmp_path / "golive")
    ok, detail = gg._gate_chargeback_package()
    assert ok, detail
    assert "matches the storefront" in detail
