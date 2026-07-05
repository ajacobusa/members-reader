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
