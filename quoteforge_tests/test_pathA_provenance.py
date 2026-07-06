"""Path A (real Gelato product photo) — the "right product, 100% validated" guarantees.

These pin the four grounded findings from the picture↔UID↔SKU audit:
  1. confirm+publish are wired AND scheduled, and a stall is detectable  (no silent stall)
  2. provenance is bound: a candidate whose image origin UID != the SKU's real UID
     can never be confirmed/published                                    (right product)
  3. a remap invalidates a published photo (stale-UID never served)      (right product)
  4. an ambiguous shared UID is dropped, never guessed                   (right product)
All local; no network, no live calls.
"""
import json

import pytest

from quoteforge.automation import mockup_sync as ms


@pytest.fixture
def cat_file(tmp_path, monkeypatch):
    f = tmp_path / "mockups.json"
    monkeypatch.setenv("MOCKUP_CATALOG_FILE", str(f))
    return f


# ── Finding 1: agent bridge wired + scheduled + stall detectable ──────────────

def test_confirm_publish_wired_and_scheduled():
    # REGRESSION: without this the daily sync leaves products at READY forever and the
    # two-agent wrong-product guard never publishes anything (silent stall).
    from quoteforge.admin import COMMANDS
    from quoteforge.automation.scheduler import SCHEDULED_JOBS
    assert "mockup-confirm" in COMMANDS and "mockup-publish" in COMMANDS
    steps = {"mockup-confirm", "mockup-publish", "mockup-pipeline"}
    assert any(j.admin_args.split()[0] in steps for j in SCHEDULED_JOBS), \
        "confirm/publish not scheduled — Path A stalls at READY, agents never publish"


def test_infra_catches_unscheduled_confirm(monkeypatch):
    # REGRESSION (the invariant catches the regression): remove the confirm/publish jobs
    # and the daily invariant must flip to ok=False.
    from quoteforge.automation import scheduler
    decoy = [j for j in scheduler.SCHEDULED_JOBS
             if j.admin_args.split()[0] not in ("mockup-confirm", "mockup-publish", "mockup-pipeline")]
    monkeypatch.setattr(scheduler, "SCHEDULED_JOBS", decoy)
    from quoteforge.automation.infra_check import check_infrastructure
    hit = [c for c in check_infrastructure()["checks"]
           if c["name"] == "mockup_confirm_publish_scheduled"]
    assert hit and hit[0]["ok"] is False


def test_agent_pending_detects_stall(cat_file):
    # A READY product with a candidate but missing verdicts is a stall signal.
    cat_file.write_text(json.dumps({"version": 1, "products": {
        "P1": {"sku": "S1", "name": "P1", "status": "ready",
               "candidate": {"src": "a.jpg", "resolved_uid": "U1"},
               "review": {"verdict": None}, "match": {"verdict": None}},
        "P2": {"sku": "S2", "name": "P2", "status": "ready",
               "candidate": {"src": "b.jpg", "resolved_uid": "U2"},
               "review": {"verdict": "PASS"}, "match": {"verdict": "MATCH"}},
    }}))
    pending = ms.agent_pending()
    assert pending == ["P1"]          # P2 has both verdicts, not stalled


# ── Finding 2: provenance is bound (right product) ────────────────────────────

def test_confirm_rejects_provenance_mismatch(cat_file, monkeypatch):
    # REGRESSION: a candidate whose image origin UID != the SKU's real UID must NOT be
    # confirmable — provenance is bound in the persisted data, not assumed.
    monkeypatch.setattr(ms, "_real_uid", lambda sku: "UID_CORRECT")
    cat_file.write_text(json.dumps({"version": 1, "products": {"P1": {
        "sku": "SKU1", "name": "P1", "status": "ready", "confirmed": False,
        "gelato_uid": "UID_CORRECT",
        "candidate": {"src": "assets/x.jpg", "fingerprint": "fp", "resolved_uid": "UID_WRONG"},
        "review": {"verdict": "PASS"}, "match": {"verdict": "MATCH"}}}}))
    ms.confirm(stamp="T")
    ms.publish(stamp="T")
    assert ms.live_mockups() == {}, "published an image whose origin UID != the SKU's UID"


def test_confirm_accepts_matching_provenance(cat_file, monkeypatch):
    # The happy path still works: a fully-verdicted candidate whose origin UID matches
    # the SKU's real UID confirms and publishes.
    monkeypatch.setattr(ms, "_real_uid", lambda sku: "UID_OK")
    cat_file.write_text(json.dumps({"version": 1, "products": {"P1": {
        "sku": "SKU1", "name": "Widget", "status": "ready", "confirmed": False,
        "gelato_uid": "UID_OK",
        "candidate": {"src": "assets/x.jpg", "fingerprint": "fp", "resolved_uid": "UID_OK",
                      "area": [0.3, 0.3, 0.4, 0.4], "cyl": False, "span": 1.9},
        "review": {"verdict": "PASS"}, "match": {"verdict": "MATCH"}}}}))
    ms.confirm(stamp="T")
    ms.publish(stamp="T")
    assert "Widget" in ms.live_mockups()


# ── Finding 3: a remap invalidates a published photo (right product) ──────────

def test_remap_invalidates_published_photo(cat_file, monkeypatch):
    # REGRESSION: after a SKU is remapped to a new UID, live_mockups() must stop serving
    # the old confirmed photo (whose bound UID no longer matches).
    cat_file.write_text(json.dumps({"version": 1, "products": {"P1": {
        "sku": "SKU1", "name": "Widget", "status": "published", "confirmed": True,
        "gelato_uid": "OLD_UID",
        "live": {"src": "assets/old.jpg", "resolved_uid": "OLD_UID"}}}}))
    monkeypatch.setattr(ms, "_real_uid", lambda sku: "NEW_UID")     # owner remapped
    assert "Widget" not in ms.live_mockups(), \
        "still serving the OLD product's photo after a remap"


# ── Finding 4: an ambiguous shared UID is dropped, never guessed ──────────────

def test_shared_uid_is_dropped_not_guessed():
    # REGRESSION: a UID shared by two SKUs must be dropped from the reverse map, never
    # guessed — else one product's photo lands on the other's tile (wrong product).
    from quoteforge.automation.gelato_sync import invert_uid_map
    inv = invert_uid_map({"GEL-TOTE-1": "UIDX", "GEL-MUG-1": "UIDX", "GEL-CAL-1": "UIDY"})
    assert "UIDX" not in inv, "ambiguous shared UID resolved to a SKU — wrong-photo risk"
    assert inv.get("UIDY") == "GEL-CAL-1"


# ── the provenance resolver reports the origin UID ────────────────────────────

def test_provenance_resolver_reports_origin_uid(monkeypatch):
    # The uid-map path reports the proven origin UID; a display-only override reports
    # source=override with uid=None (provenance unverified -> Path A holds it).
    import quoteforge.images.supplier_mockup as sm
    import quoteforge.config as cfg
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(ga, "GELATO_API_KEY", "k")
    monkeypatch.setattr(sm, "product_photo_overrides", lambda: {})
    monkeypatch.setattr(sm, "_load_cache", lambda: {"SKU1": {"uid": "UIDZ", "url": "http://x/z.jpg"}})
    monkeypatch.setattr(sm, "_save_cache", lambda c: None)
    from quoteforge.automation import gelato_sync
    monkeypatch.setattr(gelato_sync, "_uid_map", lambda: {"SKU1": "UIDZ"})
    # DB persisted path returns nothing so we reach the uid-map cache
    monkeypatch.setattr("quoteforge.db.database.get_product_images", lambda sku: [])
    prov = sm.gelato_blank_image_provenance("SKU1")
    assert prov["uid"] == "UIDZ" and prov["source"] == "uid_map"
    # gelato_blank_image (URL-only wrapper) still returns just the URL
    assert sm.gelato_blank_image("SKU1") == "http://x/z.jpg"

    monkeypatch.setattr(sm, "product_photo_overrides", lambda: {"SKU1": "http://o/ovr.jpg"})
    prov2 = sm.gelato_blank_image_provenance("SKU1")
    assert prov2["source"] == "override" and prov2["uid"] is None
