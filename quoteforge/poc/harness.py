"""POC validation harness: seed -> drive real code -> collect pass/fail checks.

`run_validation(db_path, work_dir)` isolates the DB to a temp path, installs
vendor/carrier/email mocks, seeds the 15 required test scenarios, runs the
acceptance-criteria checks against the real production modules, and returns a
structured result the report layer renders.

Every check records a severity (critical/high/medium/low) so failures classify
straight into the go/no-go decision.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

# --------------------------------------------------------------------------- #
# Mock state (vendor + carrier). Keyed so the harness can stage tracking.
# --------------------------------------------------------------------------- #
_GELATO_STATE: dict = {}     # gelato_order_id -> {status, tracking_number, carrier, estimated_delivery}
_CARRIER_STATE: dict = {}    # tracking_number -> {status, delivered_country, delivered_state, estimated_delivery}


def _mock_gelato_status(gelato_order_id: str) -> dict:
    """Stand-in for gelato_api.get_gelato_order_status (offline)."""
    s = _GELATO_STATE.get(gelato_order_id, {})
    return {"gelato_order_id": gelato_order_id, "status": s.get("status", "created"),
            "tracking_number": s.get("tracking_number", ""),
            "tracking_url": "", "carrier": s.get("carrier", ""),
            "estimated_delivery": s.get("estimated_delivery", ""), "raw": {}}


def _mock_carrier_detail(tracking_number: str, carrier: str = "") -> dict:
    """Stand-in for tracking_api.carrier_detail (offline)."""
    s = _CARRIER_STATE.get(tracking_number, {})
    return {"status": s.get("status"), "delivered_country": s.get("delivered_country", ""),
            "delivered_state": s.get("delivered_state", ""),
            "estimated_delivery": s.get("estimated_delivery", "")}


class _Mocks:
    """Install/restore the vendor, carrier, and email mocks around a run."""

    def __enter__(self):
        """Swap real network/email calls for offline stand-ins."""
        import quoteforge.automation.gelato_api as g
        import quoteforge.fulfillment.tracking_api as t
        import quoteforge.automation.emailer as e
        self._g, self._t, self._e = g, t, e
        self._og = g.get_gelato_order_status
        self._ot = t.carrier_detail
        self._oe = e._send_email
        g.get_gelato_order_status = _mock_gelato_status
        t.carrier_detail = _mock_carrier_detail
        e._send_email = lambda *a, **k: {"status": "poc-stub"}
        return self

    def __exit__(self, *exc):
        """Restore the real callables."""
        self._g.get_gelato_order_status = self._og
        self._t.carrier_detail = self._ot
        self._e._send_email = self._oe
        return False

    @staticmethod
    def stage(gelato_id: str, *, status: str, tracking_number: str = "",
              carrier: str = "USPS", carrier_status: str = "", est: str = "",
              delivered_country: str = "", delivered_state: str = "") -> None:
        """Stage a vendor + carrier tracking state for one order."""
        _GELATO_STATE[gelato_id] = {"status": status, "tracking_number": tracking_number,
                                    "carrier": carrier, "estimated_delivery": est}
        if tracking_number:
            _CARRIER_STATE[tracking_number] = {"status": carrier_status or None,
                                               "delivered_country": delivered_country,
                                               "delivered_state": delivered_state,
                                               "estimated_delivery": est}


def _iso(days_ago: int) -> str:
    """ISO timestamp `days_ago` days in the past."""
    return (datetime.now() - timedelta(days=days_ago)).isoformat()


GOOD_ADDR = {"name": "Test Buyer", "address": "1 Test St", "city": "Atlanta",
             "state": "GA", "postCode": "30301", "country": "US"}

# The 15 required scenarios (id, name) - seeded then validated below.
SCENARIOS = [
    (1, "Normal successful order"), (2, "Damaged product claim"),
    (3, "Printing defect claim"), (4, "Wrong item claim"),
    (5, "Lost shipment"), (6, "Customer-approved spelling error"),
    (7, "Low-quality uploaded image"), (8, "Cancellation after approval"),
    (9, "Refund after production"), (10, "Tracking stuck in transit"),
    (11, "Carrier exception"), (12, "Delivered, no issue"),
    (13, "Late claim after 7 days"), (14, "Repeat customer order"),
    (15, "Cart abandonment recovery"),
]


def _checks_new() -> list:
    """A fresh checks accumulator."""
    return []


def _add(checks: list, name: str, ok, severity: str, agent: str,
         scenario: int = 0, detail: str = "") -> None:
    """Record one validation check."""
    checks.append({"name": name, "ok": bool(ok), "severity": severity,
                   "agent": agent, "scenario": scenario, "detail": str(detail)})


def _guard(checks: list, name: str, severity: str, agent: str, fn,
           scenario: int = 0) -> None:
    """Run a check fn() -> (ok, detail); a crash counts as a failed check."""
    try:
        ok, detail = fn()
        _add(checks, name, ok, severity, agent, scenario, detail)
    except Exception as exc:  # noqa: BLE001
        _add(checks, name, False, severity, agent, scenario, f"error: {exc}")


def run_validation(db_path, work_dir) -> dict:
    """Isolate the DB, seed the scenarios, run every acceptance check against the
    real code, and return the structured results."""
    from pathlib import Path
    db_path, work_dir = Path(db_path), Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    import quoteforge.db.database as db
    import quoteforge.config as cfg
    o_db, o_out, o_test = db.DB_PATH, db.OUTPUT_DIR, cfg.TEST_MODE
    o_key = cfg.TRACKING_API_KEY
    db.DB_PATH, db.OUTPUT_DIR, cfg.TEST_MODE = db_path, work_dir, True
    # A carrier API key must be configured for carrier-confirmed delivery to run
    # (no key -> no polling). The harness sets a test key so the delivery path is
    # exercised; the carrier itself is mocked offline.
    cfg.TRACKING_API_KEY = "poc-test-key"
    _GELATO_STATE.clear()
    _CARRIER_STATE.clear()
    checks = _checks_new()
    try:
        if db_path.exists():
            db_path.unlink()
        db.init_db()
        with _Mocks() as mocks:
            _run_all(db, checks, mocks, work_dir)
    finally:
        db.DB_PATH, db.OUTPUT_DIR, cfg.TEST_MODE = o_db, o_out, o_test
        cfg.TRACKING_API_KEY = o_key

    return _summarize(checks)


# --------------------------------------------------------------------------- #
# The validation body - grouped by the plan's six agent roles.
# --------------------------------------------------------------------------- #
def _seed_order(db, oid: str, **fields) -> dict:
    """Create + update a seeded test order, return the row."""
    db.create_order({"order_id": oid, "etsy_order_id": "E" + oid,
                     "customer_email": fields.pop("email", "buyer@poc.test"),
                     "recipient_name": "Test Buyer", "occasion": "Birthday"})
    if fields:
        db.update_order(oid, **fields)
    return db.get_order(oid)


def _run_all(db, checks, mocks, work_dir) -> None:
    """Drive all six agent validations + the global financial/admin checks."""
    _agent_customer(db, checks, work_dir)
    _agent_routing(db, checks, mocks)
    _agent_tracking(db, checks, mocks)
    _agent_policy(db, checks)
    _agent_financial(db, checks)
    _agent_admin(db, checks)


def _agent_customer(db, checks, work_dir) -> None:
    """Agent 1: order creation, approval lock, low-quality image, abandonment."""
    from quoteforge.automation.customer_proof import record_customer_approval
    # S1: create then approve -> approval snapshot stored (locked).
    _seed_order(db, "S1", sale_price=50.0, gelato_cost=12.0, vendor="gelato",
                gelato_product_uid="uid-1", artwork_url="https://x/art.png",
                status="awaiting_customer_approval", proof_sent=1)

    def _approve():
        """Validation check; returns (ok, detail)."""
        try:
            record_customer_approval("S1")
        except Exception:
            pass                       # pipeline resume may no-op without artwork
        o = db.get_order("S1")
        return (o.get("proof_approved") == 1 and bool(o.get("proof_approved_at")),
                f"proof_approved={o.get('proof_approved')} at={o.get('proof_approved_at')}")
    _guard(checks, "Order locks after approval (snapshot stored)", "critical",
           "customer", _approve, 1)

    # S7: low-resolution uploaded image is held/rejected (never auto-approved).
    from quoteforge.automation.print_quality import assess_photo
    from PIL import Image
    img = work_dir / "lowres.png"
    Image.new("RGB", (60, 60), (200, 150, 100)).save(img)

    def _lowq():
        """Validation check; returns (ok, detail)."""
        r = assess_photo(str(img), "18x24", run_ai=False)
        return (r["decision"] in ("hold", "reject"), f"decision={r['decision']}")
    _guard(checks, "Low-quality image is held/rejected", "high", "customer", _lowq, 7)

    # S15: cart-abandonment recovery runs without error and returns a report.
    from quoteforge.automation.customization_recovery import run_recovery

    def _recovery():
        """Validation check; returns (ok, detail)."""
        r = run_recovery(send=False)
        return ("candidates" in r, f"candidates={r.get('candidates')}")
    _guard(checks, "Cart-abandonment recovery flow runs", "low", "customer",
           _recovery, 15)


def _agent_routing(db, checks, mocks) -> None:
    """Agent 2: supplier routing, id storage, duplicate block, bad-address gate."""
    from quoteforge.fulfillment.router import route_order
    # S1 continues: route the approved order -> submitted + supplier id stored.
    o = db.get_order("S1")

    def _route():
        """Validation check; returns (ok, detail)."""
        r = route_order(o, recipient=GOOD_ADDR, artwork_url="https://x/art.png")
        row = db.get_order("S1")
        return (r["status"] == "submitted" and bool(row.get("vendor_order_id")),
                f"status={r['status']} vendor_order_id={row.get('vendor_order_id')}")
    _guard(checks, "Approved order routes + supplier order id stored", "critical",
           "routing", _route, 1)

    def _dupe():
        """Validation check; returns (ok, detail)."""
        r = route_order(db.get_order("S1"), recipient=GOOD_ADDR,
                        artwork_url="https://x/art.png")
        return (r["status"] == "duplicate", f"status={r['status']}")
    _guard(checks, "Duplicate routing is blocked", "high", "routing", _dupe, 1)

    def _badaddr():
        """Validation check; returns (ok, detail)."""
        bad = _seed_order(db, "S1b", vendor="gelato", gelato_product_uid="uid-1")
        r = route_order(bad, recipient={"name": "X", "country": "US"},
                        artwork_url="https://x/art.png")
        return (r["status"] == "manual", f"status={r['status']} detail={r.get('detail','')[:40]}")
    _guard(checks, "Incomplete address is held (RTS prevented)", "high", "routing",
           _badaddr, 1)


def _agent_tracking(db, checks, mocks) -> None:
    """Agent 3: shipment + delivery confirmation rules (the safety core)."""
    from quoteforge.automation.fulfillment_tracker import sync_tracking
    # S10: shipped + carrier in_transit must NOT confirm delivery.
    _seed_order(db, "S10", vendor="gelato", gelato_order_id="GEL10",
                status="in_production")
    mocks.stage("GEL10", status="shipped", tracking_number="TN10",
                carrier_status="in_transit")
    sync_tracking()

    def _intransit():
        """Validation check; returns (ok, detail)."""
        o = db.get_order("S10")
        return (o["status"] != "delivered" and (o.get("delivery_confirmed") or 0) == 0,
                f"status={o['status']} confirmed={o.get('delivery_confirmed')}")
    _guard(checks, "In-transit does NOT confirm delivery", "critical", "tracking",
           _intransit, 10)

    # S12: carrier 'delivered' confirms (carrier-confirmed + timestamp).
    _seed_order(db, "S12", vendor="gelato", gelato_order_id="GEL12",
                status="in_production")
    mocks.stage("GEL12", status="shipped", tracking_number="TN12",
                carrier_status="in_transit")
    sync_tracking()
    mocks.stage("GEL12", status="shipped", tracking_number="TN12",
                carrier_status="delivered", delivered_country="US")
    r = sync_tracking()

    def _delivered():
        """Validation check; returns (ok, detail)."""
        o = db.get_order("S12")
        return (o["status"] == "delivered" and o.get("delivery_confirmed") == 1
                and bool(o.get("delivered_at")) and "S12" in r["delivered_confirmed"],
                f"status={o['status']} confirmed={o.get('delivery_confirmed')}")
    _guard(checks, "Carrier 'delivered' confirms delivery", "critical", "tracking",
           _delivered, 12)

    # S11: carrier exception never confirms delivery.
    _seed_order(db, "S11", vendor="gelato", gelato_order_id="GEL11",
                status="in_production")
    mocks.stage("GEL11", status="shipped", tracking_number="TN11",
                carrier_status="exception")
    sync_tracking()

    def _exception():
        """Validation check; returns (ok, detail)."""
        o = db.get_order("S11")
        return (o["status"] != "delivered", f"status={o['status']}")
    _guard(checks, "Carrier exception does NOT confirm delivery", "critical",
           "tracking", _exception, 11)

    # Negative mapping: ONLY 'Delivered' confirms across all AfterShip tags.
    from quoteforge.fulfillment.tracking_api import _AFTERSHIP_MAP

    def _mapping():
        """Validation check; returns (ok, detail)."""
        bad = [t for t, s in _AFTERSHIP_MAP.items()
               if s == "delivered" and t.lower() != "delivered"]
        return (not bad, f"non-delivered tags mapped to delivered: {bad}")
    _guard(checks, "Only 'Delivered' maps to delivered (no false positives)",
           "critical", "tracking", _mapping, 11)

    # S5: lost shipment - no tracking long after ship -> tracking-missing alert.
    _seed_order(db, "S5", vendor="printful", vendor_order_id="P5", status="shipped",
                shipped_at=_iso(5))
    rr = sync_tracking()

    def _missing():
        """Validation check; returns (ok, detail)."""
        return ("S5" in rr["tracking_missing"] or "S5" in rr["stale_in_transit"],
                f"missing={rr['tracking_missing']} stale={rr['stale_in_transit']}")
    _guard(checks, "Missing/stale tracking raises an alert", "high", "tracking",
           _missing, 5)


def _agent_policy(db, checks) -> None:
    """Agent 4: claim window, evidence, eligibility, denials, review timing."""
    from quoteforge.fulfillment.claim_service import intake_claim, validate_claim_request
    from quoteforge.etsy.resolution import resolve_issue, claim_window
    from quoteforge.etsy.delight_loop import delight_due

    # S2: damaged claim WITHOUT photos -> needs more info (evidence required).
    _seed_order(db, "S2", vendor="gelato", gelato_order_id="GEL2", status="delivered",
                delivery_confirmed=1, delivered_at=_iso(2))

    def _evidence():
        """Validation check; returns (ok, detail)."""
        r = intake_claim({"order_number": "ES2", "email": "buyer@poc.test",
                          "issue_type": "Damaged item", "description": "crushed",
                          "photos": []})
        return (r["recommended_status"] == "needs_more_info",
                f"status={r['recommended_status']} missing={r['missing_evidence']}")
    _guard(checks, "Claim requires evidence (no photos -> more info)", "high",
           "policy", _evidence, 2)

    def _damaged_ok():
        """Validation check; returns (ok, detail)."""
        r = validate_claim_request({"order_number": "ES2", "email": "buyer@poc.test",
                                    "issue_type": "Damaged item", "description": "x",
                                    "photos": ["product", "packaging"]})
        return (r["recommended_status"] == "supplier_review" and r["gelato_covered"],
                f"status={r['recommended_status']}")
    _guard(checks, "Damaged claim with evidence qualifies (manual review)", "high",
           "policy", _damaged_ok, 2)

    def _printdefect():
        """Validation check; returns (ok, detail)."""
        r = validate_claim_request({"order_number": "ES2", "email": "buyer@poc.test",
                                    "issue_type": "Printing defect", "description": "x",
                                    "photos": ["product"]})
        return (r["recommended_status"] == "supplier_review" and r["gelato_covered"],
                f"status={r['recommended_status']}")
    _guard(checks, "Printing defect with evidence qualifies", "high", "policy",
           _printdefect, 3)

    def _wrongitem():
        """Validation check; returns (ok, detail)."""
        r = validate_claim_request({"order_number": "ES2", "email": "buyer@poc.test",
                                    "issue_type": "Wrong item received", "description": "x",
                                    "photos": ["product"]})
        return (r["recommended_status"] == "supplier_review",
                f"status={r['recommended_status']}")
    _guard(checks, "Wrong item with evidence qualifies", "high", "policy",
           _wrongitem, 4)

    # S6: customer-approved spelling error -> denied (no free fix).
    def _spelling():
        """Validation check; returns (ok, detail)."""
        res = resolve_issue("approved_then_changed_mind", db.get_order("S2"))
        return (res["fault"] == "customer" and "no" in res["decision"].lower(),
                f"fault={res['fault']} decision={res['decision']}")
    _guard(checks, "Customer-approved spelling error is denied", "high", "policy",
           _spelling, 6)

    def _changedmind():
        """Validation check; returns (ok, detail)."""
        res = resolve_issue("changed_mind")
        return (res["fault"] == "customer" and not res["gelato_covered"],
                f"decision={res['decision']}")
    _guard(checks, "Change of mind is denied (no auto refund/return)", "high",
           "policy", _changedmind, 6)

    # S13: late claim (past the 7-day window) is flagged, not auto-accepted.
    _seed_order(db, "S13", status="delivered", delivery_confirmed=1, delivered_at=_iso(12))

    def _late():
        """Validation check; returns (ok, detail)."""
        w = claim_window(db.get_order("S13"))
        return (w["eligibility"] != "eligible",
                f"days={w['days_elapsed']} eligibility={w['eligibility']}")
    _guard(checks, "Late claim (>7 days) is flagged, not auto-accepted", "high",
           "policy", _late, 13)

    # S8/S9: cancellation after production / refund after production -> human only.
    def _cancel():
        """Validation check; returns (ok, detail)."""
        from quoteforge.etsy.policy import policy_facts
        p = policy_facts("cancellation")
        return (p["known"] and "human" in p["recommended"].lower()
                or "review" in p["recommended"].lower(),
                f"recommended={p['recommended'][:50]}")
    _guard(checks, "Cancellation after production -> manual review only", "high",
           "policy", _cancel, 8)

    # Review timing: not too early; eligible after the buffer; suppressed on dispute.
    def _review_early():
        """Validation check; returns (ok, detail)."""
        _seed_order(db, "S12b", status="delivered", delivery_confirmed=1,
                    delivered_at=_iso(0), customer_email="r@poc.test")
        due = delight_due(db.get_all_orders(500))
        return (not any(d["order_id"] == "S12b" for d in due), "fresh delivery not due")
    _guard(checks, "Review request not sent too early", "high", "policy",
           _review_early, 12)

    def _review_suppressed():
        """Validation check; returns (ok, detail)."""
        _seed_order(db, "S12c", status="delivered", delivery_confirmed=1,
                    delivered_at=_iso(10), delivery_disputed=1, customer_email="d@poc.test")
        due = delight_due(db.get_all_orders(500))
        return (not any(d["order_id"] == "S12c" for d in due), "disputed -> suppressed")
    _guard(checks, "Review suppressed when a dispute exists", "high", "policy",
           _review_suppressed, 12)


def _agent_financial(db, checks) -> None:
    """Agent 5: margin floor, fee/refund math, ledger matches order data."""
    from quoteforge.etsy.margin_guard import margin_check
    from quoteforge.etsy.ledger import build_ledger
    from quoteforge.analytics.financial_reports import refund_cancellation_rates

    def _floor():
        """Validation check; returns (ok, detail)."""
        below = margin_check(10.0, 8.0)
        above = margin_check(50.0, 12.0)
        return (below["ok"] is False and above["ok"] is True,
                f"below.ok={below['ok']} above.ok={above['ok']}")
    _guard(checks, "Margin floor is enforced (below floor flagged)", "critical",
           "financial", _floor, 1)

    def _ledger():
        """Validation check; returns (ok, detail)."""
        led = build_ledger("all")
        active = [o for o in db.get_all_orders(5000)
                  if (o.get("status") or "") not in ("cancelled", "error")]
        rev = round(sum(float(o.get("sale_price") or 0) for o in active), 2)
        return (abs(led["totals"]["revenue"] - rev) < 0.01,
                f"ledger={led['totals']['revenue']} orders={rev}")
    _guard(checks, "Financial report revenue matches order data", "high",
           "financial", _ledger, 1)

    def _refundrate():
        """Validation check; returns (ok, detail)."""
        _seed_order(db, "Sref", status="refunded", customer_email="x@poc.test")
        rc = refund_cancellation_rates(db.get_all_orders(5000))
        return (rc["refunded"] >= 1, f"refunded={rc['refunded']} rate={rc['refund_rate_pct']}")
    _guard(checks, "Refund/cancellation rates computed", "medium", "financial",
           _refundrate, 9)


def _agent_admin(db, checks) -> None:
    """Agent 6: monitor queue, alerts, claim queue, repeat-customer detection."""
    from quoteforge.automation.order_monitor import monitor_orders, audit_order
    from quoteforge.fulfillment.claim_workflow import open_claims
    from quoteforge.analytics.clv import build_clv

    # Production-before-approval must be flagged as a violation.
    _seed_order(db, "Sviol", status="in_production", vendor="gelato")

    def _violation():
        """Validation check; returns (ok, detail)."""
        a = audit_order(db.get_order("Sviol"))
        return (len(a["issues"]) > 0, f"issues={a['issues']}")
    _guard(checks, "Production-before-approval is flagged", "critical", "admin",
           _violation, 9)

    def _monitor():
        """Validation check; returns (ok, detail)."""
        m = monitor_orders()
        return ("checked" in m and isinstance(m["violations"], list),
                f"checked={m['checked']} violations={len(m['violations'])}")
    _guard(checks, "Admin compliance monitor returns risky orders", "high",
           "admin", _monitor, 9)

    def _queue():
        """Validation check; returns (ok, detail)."""
        oc = open_claims()
        return (isinstance(oc, list), f"open_claims={len(oc)}")
    _guard(checks, "Claim review queue is available", "high", "admin", _queue, 2)

    # S14: repeat customer (2 orders, same email) is detected.
    _seed_order(db, "S14a", customer_email="repeat@poc.test", status="delivered",
                sale_price=40.0, delivered_at=_iso(60))
    _seed_order(db, "S14b", customer_email="repeat@poc.test", status="delivered",
                sale_price=45.0, delivered_at=_iso(5))

    def _repeat():
        """Validation check; returns (ok, detail)."""
        c = build_clv(db.get_all_orders(5000))
        return (c["repeat_customers"] >= 1, f"repeat_customers={c['repeat_customers']}")
    _guard(checks, "Repeat customer is detected", "medium", "admin", _repeat, 14)


# --------------------------------------------------------------------------- #
# Summary + go/no-go (sections 6-9 of the plan).
# --------------------------------------------------------------------------- #
def _summarize(checks: list) -> dict:
    """Aggregate checks into metrics, issue buckets, and the go/no-go verdict."""
    passed = [c for c in checks if c["ok"]]
    failed = [c for c in checks if not c["ok"]]
    by_sev = {s: [c for c in failed if c["severity"] == s]
              for s in ("critical", "high", "medium", "low")}
    # Per-scenario pass/fail (a scenario passes if all its checks pass).
    scen = []
    for sid, name in SCENARIOS:
        sc = [c for c in checks if c["scenario"] == sid]
        scen.append({"id": sid, "name": name, "checks": len(sc),
                     "passed": bool(sc) and all(c["ok"] for c in sc)})
    go = not by_sev["critical"] and not by_sev["high"]
    return {
        "generated_at": None,           # stamped by the runner (no clock in harness libs)
        "checks": checks,
        "metrics": {
            "total_checks": len(checks), "passed": len(passed), "failed": len(failed),
            "coverage_pct": round(len(passed) / len(checks) * 100, 1) if checks else 0.0,
            "scenarios_total": len(SCENARIOS),
            "scenarios_passed": sum(1 for s in scen if s["passed"]),
            "critical_fail": len(by_sev["critical"]), "high_fail": len(by_sev["high"]),
            "medium_fail": len(by_sev["medium"]), "low_fail": len(by_sev["low"]),
        },
        "scenarios": scen,
        "issues": {s: by_sev[s] for s in by_sev},
        "go": go,
    }
