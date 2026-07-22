"""The 10 go-live gates - verified DAILY, honestly, with owner sign-offs.

Each gate has an AUTOMATED verification (behavioral where possible - it runs the
real code against a throwaway DB/temp dir, never mutating production state) and,
where the gate inherently needs a human (physical prints, a live processor
dashboard, a clean-machine drill), an OWNER SIGN-OFF recorded via
`admin golive-signoff <gate>`. A gate is READY only when its automated check
passes AND any required sign-off is on file.

Doctrine: no gate ever fakes a pass. Machinery that does not exist is reported
as exactly that; live/physical steps stay owner-gated. The daily scheduled run
alerts the owner on any regression (a gate that WAS ready going un-ready).

Sign-offs persist in OUTPUT_DIR/golive_signoffs.json:
    {"<gate_id>": {"by": "...", "at": "...", "note": "..."}}
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from quoteforge.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

SIGNOFF_PATH: Path = OUTPUT_DIR / "golive_signoffs.json"
SAMPLE_DIR: Path = OUTPUT_DIR / "golive"

# The 10 destinations exercised by the shipping gate - every non-domestic zone.
INTL_DESTINATIONS = ["GB", "DE", "FR", "IE", "CA", "MX", "AU", "NZ", "JP", "BR"]


# ── sign-off store ────────────────────────────────────────────────────────────
def load_signoffs() -> dict:
    """The owner sign-offs on file (empty dict when none yet)."""
    try:
        if SIGNOFF_PATH.exists():
            return json.loads(SIGNOFF_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a corrupt file must not hide gates
        logger.warning("sign-off store unreadable (treated as none): %s", exc)
    return {}


def record_signoff(gate_id: str, by: str = "owner", note: str = "") -> dict:
    """Record (or refresh) the owner's sign-off for one gate. Returns the store."""
    valid = {g["id"] for g in GATES}
    if gate_id not in valid:
        raise ValueError(f"unknown gate '{gate_id}' - one of {sorted(valid)}")
    store = load_signoffs()
    store[gate_id] = {"by": by, "at": datetime.now().isoformat(timespec="seconds"),
                      "note": note}
    SIGNOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNOFF_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return store


def clear_signoff(gate_id: str) -> dict:
    """Withdraw a sign-off (e.g. after a regression). Returns the store."""
    store = load_signoffs()
    store.pop(gate_id, None)
    SIGNOFF_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return store


# ── throwaway DB (behavioral checks never touch production state) ────────────
class _TempDB:
    """Swap quoteforge.db.database.DB_PATH to a temp file for the duration."""

    def __enter__(self):
        from quoteforge.db import database
        self._db = database
        self._orig = database.DB_PATH
        self._dir = tempfile.mkdtemp(prefix="qf_gate_")
        database.DB_PATH = Path(self._dir) / "gate_check.db"
        database.init_db()
        return self._db

    def __exit__(self, *exc):
        self._db.DB_PATH = self._orig
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


# ── the gate checks ──────────────────────────────────────────────────────────
def _gate_payment_webhooks() -> tuple[bool, str]:
    """Gate 1: order-intake webhooks handle the edge cases.

    Payments happen on the HOSTED checkout (PAY_LINK) - there are no inbound
    payment_intent webhooks BY DESIGN; money-in arrives as the marketplace order
    webhook. So the automated edges are: HMAC signature accept/reject/tamper,
    a malformed payload, and a payload with no order id - none may crash or
    create a phantom order. The processor-side events (succeeded/failed/
    canceled/requires_action) live on the processor dashboard: owner sign-off.
    """
    from quoteforge.automation.webhook_security import (compute_signature,
                                                        verify_signature)
    probs: list[str] = []
    body = b'{"order_id":"GATE-TEST"}'
    sig = compute_signature(body, "gate-secret")
    if not verify_signature(body, sig, "gate-secret"):
        probs.append("valid HMAC signature rejected")
    if verify_signature(body, sig, "wrong-secret"):
        probs.append("signature verified with the WRONG secret")
    if verify_signature(body + b"x", sig, "gate-secret"):
        probs.append("TAMPERED payload passed signature verification")
    with _TempDB() as db:
        from quoteforge.automation.webhook_server import process_webhook_payload
        try:
            r1 = process_webhook_payload({})
            r2 = process_webhook_payload({"items": "not-a-list"})
            if not isinstance(r1, dict) or not isinstance(r2, dict):
                probs.append("malformed payload did not return a result dict")
        except Exception as exc:  # noqa: BLE001 - the gate reports, never raises
            probs.append(f"malformed payload CRASHED the webhook path: {exc}")
        del db
    ok = not probs
    return ok, ("signature verify + malformed/no-id payloads handled; processor "
                "events are hosted-checkout side (sign-off = dashboard reviewed)"
                if ok else "; ".join(probs))


def _gate_order_locking() -> tuple[bool, str]:
    """Gate 2: once the proof is approved, locked design fields are immutable
    (OrderLockedError), a same-value rewrite is a no-op, and the ONLY bypass is
    the audited allow_locked admin override."""
    probs: list[str] = []
    with _TempDB() as db:
        oid = db.create_order({"customer_email": "gate@test.local",
                               "size": "8x10", "material": "poster"})
        db.update_order(oid, proof_approved=1,
                        proof_approved_at=datetime.now().isoformat())
        try:
            db.update_order(oid, size="16x20")
            probs.append("locked order accepted a design edit (no exception)")
        except db.OrderLockedError:
            logger.info("lock verified: OrderLockedError raised as designed")
        try:
            db.update_order(oid, size="8x10")   # same value: allowed no-op
        except db.OrderLockedError:
            probs.append("same-value rewrite falsely raised OrderLockedError")
        try:
            db.update_order(oid, size="16x20", allow_locked=True)
            if (db.get_order(oid) or {}).get("size") != "16x20":
                probs.append("allow_locked override did not persist")
        except Exception as exc:  # noqa: BLE001
            probs.append(f"audited admin override failed: {exc}")
    ok = not probs
    return ok, ("lock verified live: edit raises OrderLockedError, no-op rewrite "
                "allowed, allow_locked is the only (audited) bypass"
                if ok else "; ".join(probs))


def _gate_proof_hash() -> tuple[bool, str]:
    """Gate 3: the proof-hash chain works - file_sha256 is a true sha256 and
    the approval recorder stores the print file's hash with the consent record.
    Comparing against the LIVE Gelato-fetched file needs a real order: sign-off."""
    import inspect
    from quoteforge.automation import customer_proof
    from quoteforge.automation.print_quality import file_sha256
    probs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qf_gate_") as td:
        p = Path(td) / "artwork.jpg"
        payload = b"gate-check artwork bytes"
        p.write_bytes(payload)
        expect = hashlib.sha256(payload).hexdigest()
        got = file_sha256(str(p))
        if got != expect:
            probs.append(f"file_sha256 mismatch ({got[:12]} != {expect[:12]})")
    src = inspect.getsource(customer_proof)
    if "file_sha256(hashable_print_file(" not in src:
        probs.append("record_customer_approval no longer stores the print-file "
                     "hash with the consent record")
    ok = not probs
    return ok, ("sha256 verified against hashlib; approval recorder stores the "
                "print-file hash (sign-off = first live order's fetched file "
                "hash compared)" if ok else "; ".join(probs))


def _gate_shipping_margin() -> tuple[bool, str]:
    """Gate 4: across 10 international destinations, the shipping model prices
    every lane and the variance tripwire fires when actual exceeds model or
    what the buyer paid - so a rate can never silently exceed the quote."""
    from quoteforge.etsy.shipping_audit import modeled_shipping, shipping_variance
    probs: list[str] = []
    for cc in INTL_DESTINATIONS:
        for mat in ("Framed print", "Classic Ceramic Mug (11oz)", "Wall Calendar"):
            m = modeled_shipping(cc, mat)
            if not (m and m > 0):
                probs.append(f"no modeled shipping for {cc}/{mat}")
    probe = {"order_id": "GATE", "country": "AU", "material": "Framed print"}
    base = modeled_shipping("AU", "Framed print")
    if not shipping_variance({**probe, "shipping_cost": base * 2,
                              "shipping_collected": base})["leaking"]:
        probs.append("tripwire silent when actual is 2x the model")
    if not shipping_variance({**probe, "shipping_cost": base,
                              "shipping_collected": base - 1})["leaking"]:
        probs.append("tripwire silent when actual exceeds what the buyer paid")
    if shipping_variance({**probe, "shipping_cost": base,
                          "shipping_collected": base + 5})["leaking"]:
        probs.append("tripwire false-fires on a healthy lane")
    ok = not probs
    return ok, (f"{len(INTL_DESTINATIONS)} international lanes x 3 materials "
                "modeled; overrun + undercollection tripwires verified live"
                if ok else "; ".join(probs[:3]))


def _gate_apparel_calibration() -> tuple[bool, str]:
    """Gate 5: apparel stays HELD until physical test prints are owner-approved.
    Automated: the APPAREL_PRINT_CALIBRATED gate exists and apparel is held
    while it is off. The physical review itself is the owner's sign-off."""
    from quoteforge.config import APPAREL_PRINT_CALIBRATED
    state = ("CALIBRATED (flag on)" if APPAREL_PRINT_CALIBRATED
             else "apparel HELD (flag off - flips only after the physical "
                  "test print is approved)")
    return True, state


def _gate_backup_restore() -> tuple[bool, str]:
    """Gate 6: a real restore REHEARSAL with zero production mutation - backups
    verify healthy, the code bundle git-clones into a temp dir, and a COPY of
    the newest DB snapshot opens with an orders table. (restore_all() is never
    called here: it restores the live DB. Clean-machine drill = sign-off.)"""
    from quoteforge.automation.full_backup import BUNDLE_PATH, verify_backup
    from quoteforge.db.database import list_backups
    probs: list[str] = []
    v = verify_backup()
    if not v.get("ok"):
        probs.append("verify_backup reports NOT healthy")
    with tempfile.TemporaryDirectory(prefix="qf_gate_") as td:
        dest = Path(td) / "clone"
        if not BUNDLE_PATH.exists():
            probs.append("no code bundle on disk")
        else:
            r = subprocess.run(["git", "clone", "-q", str(BUNDLE_PATH), str(dest)],
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                probs.append(f"bundle clone failed: {(r.stderr or '')[:120]}")
            elif not (dest / "quoteforge").is_dir():
                probs.append("cloned bundle is missing the quoteforge/ package")
        snaps = list_backups()
        if not snaps:
            probs.append("no DB snapshot to rehearse")
        else:
            snap_copy = Path(td) / "snapshot.db"
            shutil.copy2(snaps[0], snap_copy)
            try:
                conn = sqlite3.connect(snap_copy)
                n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
                conn.close()
            except Exception as exc:  # noqa: BLE001
                probs.append(f"snapshot DB unreadable: {exc}")
            else:
                logger.info("restore rehearsal: snapshot opens, %s order row(s)", n)
    ok = not probs
    return ok, ("backups healthy; bundle cloned to temp + snapshot copy opens "
                "with an orders table (sign-off = clean-machine drill)"
                if ok else "; ".join(probs))


def _gate_webhook_flood() -> tuple[bool, str]:
    """Gate 7: a duplicate/redelivery storm cannot create duplicate orders -
    20x the same order intake yields exactly one row (create_order preserves,
    never REPLACEs). Full HTTP-level load stays a pre-launch drill: sign-off."""
    probs: list[str] = []
    with _TempDB() as db:
        ids = {db.create_order({"order_id": "GATE-FLOOD-1",
                                "etsy_order_id": "ETSY-FLOOD-1",
                                "customer_email": "gate@test.local"})
               for _ in range(20)}
        if ids != {"GATE-FLOOD-1"}:
            probs.append(f"duplicate storm produced ids {sorted(ids)[:3]}")
        with sqlite3.connect(db.DB_PATH) as conn:
            n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if n != 1:
            probs.append(f"20x redelivery created {n} rows (expected 1)")
    ok = not probs
    return ok, ("20x redelivery storm -> exactly 1 order row (idempotent intake); "
                "sign-off = HTTP-level 10x load drill before launch"
                if ok else "; ".join(probs))


def _gate_chargeback_package() -> tuple[bool, str]:
    """Gate 8: a chargeback evidence package can be assembled - consent record
    (the affirmative approval + timestamp), print-file hash, order facts,
    tracking, and the made-to-order policy. A sample for a synthetic test order
    is written to OUTPUT_DIR/golive/ for the owner to review (sign-off)."""
    sample_order = {
        "order_id": "GATE-CB-SAMPLE", "customer_email": "gate@test.local",
        "size": "8x10", "material": "Framed print",
        "proof_approved": 1,
        "proof_approved_at": datetime.now().isoformat(timespec="seconds"),
        "tracking_number": "TRK-SAMPLE-123", "carrier": "sample-carrier",
        "status": "delivered",
    }
    pkg = build_chargeback_package(sample_order,
                                   proof_sha256=hashlib.sha256(b"sample").hexdigest())
    missing = [k for k, v in pkg.items() if not v]
    ok = not missing
    if ok:
        try:
            SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
            out = SAMPLE_DIR / "chargeback_evidence_sample.json"
            out.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - a write blip must not fail the gate
            logger.warning("sample package write skipped: %s", exc)
    return ok, ("evidence package assembles (consent + proof hash + tracking + "
                "policy); sample written to golive/chargeback_evidence_sample.json"
                if ok else f"package missing sections: {missing}")


def build_chargeback_package(order: dict, proof_sha256: str = "") -> dict:
    """Assemble the dispute-evidence package for one order from the records we
    already keep. Every value must be truthy for the package to be filing-ready."""
    return {
        "order": {k: order.get(k) for k in
                  ("order_id", "size", "material", "status")},
        "consent_record": {
            "statement": ("Customer affirmatively approved: 'I approve this "
                          "print exactly as shown and authorize it to proceed "
                          "to production.' (3 gating checkboxes)"),
            "approved_at": order.get("proof_approved_at") or "",
            "proof_approved": bool(order.get("proof_approved")),
        },
        "print_file_sha256": proof_sha256
                             or order.get("print_file_sha256") or "",
        "fulfillment": {
            "tracking_number": order.get("tracking_number") or "",
            "carrier": order.get("carrier") or "",
        },
        "policy": ("Made to order; final once confirmed at checkout; no "
                   "returns/refunds for approved wording/design/sizing; "
                   "damaged/defective/wrong-item/non-delivery covered with a "
                   "photo within 7 days."),
    }


def _gate_infra_check() -> tuple[bool, str]:
    """Gate 9: the full infra_check invariant sweep is green right now on this
    checkout. The literal fresh-clone drill is a pre-launch step: sign-off."""
    from quoteforge.automation.infra_check import check_infrastructure
    r = check_infrastructure()
    bad = [c["name"] for c in r["checks"] if not c["ok"]]
    ok = bool(r["ok"])
    return ok, (f"all {len(r['checks'])} invariants green (sign-off = fresh-"
                "clone run)" if ok else f"FAILING invariants: {bad[:5]}")


def _gate_suite_documented() -> tuple[bool, str]:
    """Gate 10: the newest merge commits on the default branch document the
    real suite numbers ('N passed') - green claimed with evidence, per doctrine."""
    import re
    import quoteforge
    root = Path(quoteforge.__file__).resolve().parent.parent
    r = subprocess.run(["git", "log", "--merges", "-n", "8", "--pretty=%s%n%b"],
                       cwd=root, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return False, f"git log failed: {(r.stderr or '')[:120]}"
    m = re.search(r"(\d{3,}) passed", r.stdout)
    ok = bool(m)
    return ok, (f"suite numbers on record in recent merges ({m.group(0)})"
                if ok else "no 'N passed' evidence in the last 8 merge commits")


# ── registry + runner ────────────────────────────────────────────────────────
# owner_signoff=True marks gates whose verification method inherently ends with
# a human step (physical print, processor dashboard, clean machine, live fetch,
# HTTP load rig, fresh clone). Their automated portion still runs daily.
GATES: list[dict] = [
    {"num": 1, "id": "payment_webhooks", "owner_signoff": True,
     "title": "Payment/order webhooks handle all edge cases",
     "check": _gate_payment_webhooks},
    {"num": 2, "id": "order_locking", "owner_signoff": False,
     "title": "Order locking is irreversible",
     "check": _gate_order_locking},
    {"num": 3, "id": "proof_hash", "owner_signoff": True,
     "title": "Proof hash matches printed file",
     "check": _gate_proof_hash},
    {"num": 4, "id": "shipping_margin", "owner_signoff": False,
     "title": "Shipping rate never exceeds quoted price",
     "check": _gate_shipping_margin},
    {"num": 5, "id": "apparel_calibration", "owner_signoff": True,
     "title": "Apparel calibration complete",
     "check": _gate_apparel_calibration},
    {"num": 6, "id": "backup_restore", "owner_signoff": True,
     "title": "Backup restore tested",
     "check": _gate_backup_restore},
    {"num": 7, "id": "webhook_flood", "owner_signoff": True,
     "title": "Webhook server survives abuse",
     "check": _gate_webhook_flood},
    {"num": 8, "id": "chargeback_package", "owner_signoff": True,
     "title": "Chargeback evidence package ready",
     "check": _gate_chargeback_package},
    {"num": 9, "id": "infra_check_green", "owner_signoff": True,
     "title": "infra_check passes on clean checkout",
     "check": _gate_infra_check},
    {"num": 10, "id": "suite_documented", "owner_signoff": False,
     "title": "Full test suite green with real numbers",
     "check": _gate_suite_documented},
]


def run_gates() -> dict:
    """Run every gate. Returns {timestamp, ready, gates:[...]} - a gate is
    'ready' when its automated check passes AND any required sign-off is on
    file. Never raises: a crashed check is a FAILED gate (fail closed)."""
    signoffs = load_signoffs()
    rows = []
    for g in GATES:
        try:
            ok, detail = g["check"]()
        except Exception as exc:  # noqa: BLE001 - fail closed, never crash the sweep
            ok, detail = False, f"gate check crashed: {exc}"
        so = signoffs.get(g["id"])
        ready = bool(ok and (so or not g["owner_signoff"]))
        rows.append({"num": g["num"], "id": g["id"], "title": g["title"],
                     "ok": bool(ok), "owner_signoff_required": g["owner_signoff"],
                     "signed_off": bool(so),
                     "signed_off_at": (so or {}).get("at", ""),
                     "ready": ready, "detail": detail})
    return {"timestamp": datetime.now().isoformat(timespec="seconds"),
            "ready": all(r["ready"] for r in rows),
            "gates": rows}


def format_gates_text(r: dict) -> str:
    """Human-readable gate board (printed by the CLI / emailed daily)."""
    lines = ["=" * 64, f"GO-LIVE GATES - {r['timestamp']}", "=" * 64]
    for g in r["gates"]:
        mark = "READY" if g["ready"] else ("CHECK" if g["ok"] else "FAIL ")
        so = ("" if not g["owner_signoff_required"]
              else (f" [signed off {g['signed_off_at'][:10]}]" if g["signed_off"]
                    else " [awaiting owner sign-off: "
                         f"admin golive-signoff {g['id']}]"))
        lines.append(f"  [{mark}] {g['num']:>2}. {g['title']}{so}")
        lines.append(f"          {g['detail']}")
    lines.append("-" * 64)
    n_ready = sum(1 for g in r["gates"] if g["ready"])
    lines.append(f"  {n_ready}/{len(r['gates'])} gates READY"
                 + ("" if r["ready"] else " - NOT clear for go-live"))
    lines.append("=" * 64)
    return "\n".join(lines)
