"""Gelato live-seam ops (Components 2-4) - defensive, gated, spend-capped.

Safety invariants: every function is a no-op in TEST_MODE / without a key; the provider
seams never raise on an unexpected shape; and the money-out test order fires ONLY with the
explicit consent, a real UID, a cost within the cap, idempotently, through the SAME
idempotent router a customer order uses. Isolated DB per test.
"""
import pytest

from quoteforge.automation import gelato_live_ops as ops


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    import quoteforge.db.database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "qf.db")
    db.init_db()
    return tmp_path


# ── Component 2: create ──────────────────────────────────────────

def test_create_no_op_in_test_mode(iso_db):
    assert "skipped" in ops.create_first_live_product("tmpl", "Tee")


def test_create_records_probe_and_is_idempotent(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.GELATO_STORE_ID", "store_1")
    r = ops.create_first_live_product("tmpl", "Tee", creator=lambda: {"id": "gp_1"})
    assert r["created"] is True and r["gelato_product_id"] == "gp_1"
    # second call must NOT create again (idempotent) - a probe exists
    r2 = ops.create_first_live_product("tmpl", "Tee", creator=lambda: {"id": "gp_2"})
    assert "skipped" in r2 and r2["probe_id"] == r["probe_id"]


def test_create_defensive_on_bad_shape(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.GELATO_STORE_ID", "store_1")
    # a create response with no id -> recorded as create_failed, never raises
    r = ops.create_first_live_product("tmpl", "Tee", creator=lambda: {"unexpected": True})
    assert r["created"] is False


# ── Component 3: image-shape sync ────────────────────────────────

def test_sync_records_shape(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.GELATO_STORE_ID", "store_1")
    ops.create_first_live_product("tmpl", "Tee", creator=lambda: {"id": "gp_1"})
    s = ops.sync_live_image_shapes(
        gelato_fetch=lambda pid: {"externalId": "L1"},
        etsy_fetch=lambda p: {"images": [{"url": "http://x/y.png"}]})
    assert s["detected_image_shape"].startswith("images:list[dict:")
    assert s["status"] == "image_shape_confirmed"


def test_sync_no_op_without_probe(iso_db):
    assert "skipped" in ops.sync_live_image_shapes(
        gelato_fetch=lambda pid: {}, etsy_fetch=lambda p: {})


# ── Component 4: spend-capped physical test order ────────────────

def _ok_router(o, r, a):
    return {"status": "submitted", "id": "vendor_1"}


def test_test_order_blocked_without_consent(iso_db):
    assert "blocked" in ops.submit_calibration_test_order(
        "real_uid", {"name": "A"}, "http://x/a.png", est_cost=15, router=_ok_router)


def test_test_order_rejects_placeholder_and_over_cap(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.CALIBRATION_TEST_ORDER_ENABLED", True)
    assert "blocked" in ops.submit_calibration_test_order(
        "GEL-SEED", {"name": "A"}, "http://x/a.png", est_cost=15, router=_ok_router)
    over = ops.submit_calibration_test_order(
        "real_uid", {"name": "A"}, "http://x/a.png", est_cost=999, router=_ok_router)
    assert "blocked" in over and "cap" in over["blocked"]
    assert "blocked" in ops.submit_calibration_test_order(   # unknown cost -> blocked
        "real_uid", {"name": "A"}, "http://x/a.png", est_cost=0, router=_ok_router)


def test_test_order_places_once_then_idempotent(iso_db, monkeypatch):
    monkeypatch.setattr("quoteforge.config.CALIBRATION_TEST_ORDER_ENABLED", True)
    calls = []
    def router(o, r, a):
        calls.append(o)
        return {"status": "submitted", "id": "vendor_1"}
    r = ops.submit_calibration_test_order(
        "real_uid", {"name": "A"}, "http://x/a.png", est_cost=15, router=router)
    assert r["ordered"] is True and r["vendor_id"] == "vendor_1"
    # a calibration row now exists -> a re-run must NOT place a second order
    r2 = ops.submit_calibration_test_order(
        "real_uid", {"name": "A"}, "http://x/a.png", est_cost=15, router=router)
    assert "blocked" in r2 and len(calls) == 1


def test_test_order_uid_unique_index_refuses_duplicate(iso_db):
    # REGRESSION (audit High): the idempotency guarantee must be DB-enforced. A UNIQUE
    # index on an OPEN (pending/test_ordered) product_uid is what makes a concurrent
    # double-order impossible; the caller-side COUNT alone is a TOCTOU check.
    import sqlite3
    import quoteforge.db.database as db
    with db._conn() as c:
        c.execute("INSERT INTO apparel_print_calibration (product_uid, status) "
                  "VALUES ('U','test_ordered')")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO apparel_print_calibration (product_uid, status) "
                      "VALUES ('U','pending')")


def test_failed_route_releases_reservation(iso_db, monkeypatch):
    # A blocked/failed route must NOT leave a phantom 'pending' block - a corrected retry
    # can proceed, and no 'test_ordered' row is recorded on failure.
    monkeypatch.setattr("quoteforge.config.CALIBRATION_TEST_ORDER_ENABLED", True)
    r = ops.submit_calibration_test_order(
        "real_uid", {"name": "A"}, "http://x/a.png", est_cost=15,
        router=lambda o, r, a: {"status": "manual", "id": ""})
    assert r["ordered"] is False
    import quoteforge.db.database as db
    with db._conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM apparel_print_calibration "
                      "WHERE product_uid='real_uid'").fetchone()["n"]
    assert n == 0                                   # reservation released, no phantom block


def test_doctor_pre_go_live_reports_blockers(iso_db):
    d = ops.first_product_doctor()
    assert d["ready"] is False and d["next_action"]
    names = {c["name"] for c in d["checks"]}
    assert {"gelato_api_key", "live_mode", "gelato_store_id", "approved_uid"} <= names
    assert "dashboard" in d["easier_path"].lower()


def _go_live(monkeypatch):
    monkeypatch.setattr("quoteforge.config.TEST_MODE", False)
    monkeypatch.setattr("quoteforge.config.GELATO_API_KEY", "k")
    monkeypatch.setattr("quoteforge.automation.gelato_api.GELATO_API_KEY", "k")
    monkeypatch.setattr("quoteforge.config.GELATO_STORE_ID", "store_1")


def test_doctor_flags_missing_template(iso_db, monkeypatch):
    # live + catalog + store reachable, an approved UID exists, but NO template -> the
    # doctor pinpoints the template as the blocker (the usual "keeps not resolving").
    _go_live(monkeypatch)
    from quoteforge.automation.gelato_readiness import map_real_gelato_uid
    map_real_gelato_uid("apparel", "GEL-A", "real_a")           # approved on write
    d = ops.first_product_doctor(
        probe=lambda: {"catalog_ok": True, "store_ok": True, "templates": []})
    by = {c["name"]: c for c in d["checks"]}
    assert by["template_exists"]["ok"] is False and "dashboard" in by["template_exists"]["fix"]
    assert by["catalog_reachable"]["ok"] and by["store_reachable"]["ok"]
    assert d["ready"] is False


def test_doctor_all_green_when_everything_present(iso_db, monkeypatch):
    _go_live(monkeypatch)
    from quoteforge.automation.gelato_readiness import map_real_gelato_uid
    map_real_gelato_uid("apparel", "GEL-A", "real_a")
    d = ops.first_product_doctor(
        probe=lambda: {"catalog_ok": True, "store_ok": True, "templates": [{"id": "t1"}]})
    assert d["ready"] is True and not d["next_action"]


def test_doctor_never_raises_on_probe_error(iso_db, monkeypatch):
    _go_live(monkeypatch)
    def boom():
        raise RuntimeError("gelato down")
    d = ops.first_product_doctor(probe=boom)   # a crashing probe must not crash the doctor
    assert d["ready"] is False                 # fails safe to not-ready


def test_test_order_routes_apparel_through_router(iso_db, monkeypatch):
    # the order handed to the router must be a real-UID apparel order (so it rides the
    # same GEL-* / calibration / idempotency gates a customer order does).
    monkeypatch.setattr("quoteforge.config.CALIBRATION_TEST_ORDER_ENABLED", True)
    seen = {}
    def router(o, r, a):
        seen.update(o)
        return {"status": "submitted", "id": "v1"}
    ops.submit_calibration_test_order("real_uid", {"name": "A"}, "http://x/a.png",
                                      est_cost=15, router=router)
    assert seen["product_type"] == "apparel" and seen["gelato_product_uid"] == "real_uid"
    assert seen.get("calibration_test") is True
