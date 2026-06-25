"""Gelato mockup sync engine — guard rails + the per-product state machine.

The invariants that protect production: no-op until genuinely live, NEVER publish a
product the two agents haven't confirmed, a changed Gelato image re-queues for
re-confirmation, and only a re-hosted same-origin path ever reaches the build.
"""
import json

import pytest

from quoteforge.automation import mockup_sync as ms


@pytest.fixture
def cat_file(tmp_path, monkeypatch):
    f = tmp_path / "mockups.json"
    monkeypatch.setenv("MOCKUP_CATALOG_FILE", str(f))
    return f


def _go_live(monkeypatch, uid="real_uid_123"):
    """Force the engine into 'live' with a real UID for every SKU."""
    monkeypatch.setattr(ms, "_live_gated", lambda: True)
    monkeypatch.setattr(ms, "_real_uid", lambda sku: uid)


def _fakes(fingerprint="fp1", url="https://cdn.gelato/x.png"):
    fetch = lambda sku: url                                   # noqa: E731
    rehost = lambda u, pid: (f"assets/mockups/{pid}.jpg", fingerprint)  # noqa: E731
    printarea = lambda uid: None                             # noqa: E731 (force defaults)
    return fetch, rehost, printarea


# ── Guard rail: no-op until genuinely live ───────────────────────────────

def test_test_mode_is_a_no_op(cat_file, monkeypatch):
    monkeypatch.setattr(ms, "_live_gated", lambda: False)
    monkeypatch.setattr(ms, "_real_uid", lambda sku: None)   # placeholder world
    s = ms.run_sync(stamp="T")
    assert s["fetched"] == 0 and s["ready"] == 0
    assert s["skipped"] >= 1                                  # all skip on the UID guard
    assert ms.live_mockups() == {}                           # nothing can show


def test_placeholder_uid_is_skipped_even_when_live(cat_file, monkeypatch):
    monkeypatch.setattr(ms, "_live_gated", lambda: True)
    monkeypatch.setattr(ms, "_real_uid", lambda sku: None)   # GEL-* placeholder
    fetch, rehost, printarea = _fakes()
    s = ms.run_sync(stamp="T", fetch_image=fetch, rehost=rehost, printarea=printarea)
    assert s["fetched"] == 0 and s["ready"] == 0 and s["skipped"] >= 1
    assert ms.live_mockups() == {}


# ── Live flow: sync → confirm → publish ──────────────────────────────────

def test_full_flow_two_agents_confirm_then_publish(cat_file, monkeypatch):
    _go_live(monkeypatch)
    fetch, rehost, printarea = _fakes(fingerprint="fpA")
    s = ms.run_sync(stamp="T1", fetch_image=fetch, rehost=rehost, printarea=printarea)
    assert s["ready"] >= 1 and s["fetched"] >= 1

    # pick a real product id from the catalog
    rows = ms.review_rows()
    pid = next(r["product_id"] for r in rows if r["status"] == "ready")

    # before agents agree, nothing publishes
    ms.confirm(stamp="T1")
    ms.publish(stamp="T1")
    assert ms.live_mockups() == {}, "published before confirmation!"

    # both agents agree → confirmed → published → live
    ms.apply_verdicts(pid, review="PASS", match="MATCH", stamp="T1")
    cs = ms.confirm(stamp="T1")
    assert cs["confirmed"] >= 1
    ps = ms.publish(stamp="T1")
    assert ps["published"] >= 1
    live = ms.live_mockups()
    name = next(r for r in ms.review_rows() if r["product_id"] == pid)
    # the published product appears in live_mockups, keyed by name, local src only
    assert any(v["src"].startswith("assets/mockups/") for v in live.values())
    assert all("gelato" not in v["src"].lower() for v in live.values())   # no leak


def test_one_agent_failing_holds_and_never_publishes(cat_file, monkeypatch):
    _go_live(monkeypatch)
    fetch, rehost, printarea = _fakes()
    ms.run_sync(stamp="T", fetch_image=fetch, rehost=rehost, printarea=printarea)
    pid = next(r["product_id"] for r in ms.review_rows() if r["status"] == "ready")
    # reviewer PASS but match MISMATCH → held
    ms.apply_verdicts(pid, review="PASS", match="MISMATCH", stamp="T")
    ms.confirm(stamp="T"); ms.publish(stamp="T")
    assert ms.live_mockups() == {}
    row = next(r for r in ms.review_rows() if r["product_id"] == pid)
    assert row["status"] == "held" and row["confirmed"] is False


def test_missing_verdict_is_pending_not_confirmed(cat_file, monkeypatch):
    _go_live(monkeypatch)
    fetch, rehost, printarea = _fakes()
    ms.run_sync(stamp="T", fetch_image=fetch, rehost=rehost, printarea=printarea)
    pid = next(r["product_id"] for r in ms.review_rows() if r["status"] == "ready")
    ms.apply_verdicts(pid, review="PASS", stamp="T")        # only one verdict
    cs = ms.confirm(stamp="T"); ms.publish(stamp="T")
    assert cs["confirmed"] == 0
    assert ms.live_mockups() == {}


# ── Guard rail: a changed Gelato image re-queues for re-confirmation ──────

def test_changed_image_requeues_confirmation(cat_file, monkeypatch):
    _go_live(monkeypatch)
    # publish a product
    f1, r1, pa = _fakes(fingerprint="fpV1")
    ms.run_sync(stamp="T1", fetch_image=f1, rehost=r1, printarea=pa)
    pid = next(r["product_id"] for r in ms.review_rows() if r["status"] == "ready")
    ms.apply_verdicts(pid, review="PASS", match="MATCH", stamp="T1")
    ms.confirm(stamp="T1"); ms.publish(stamp="T1")
    assert ms.live_mockups(), "should be live after first confirm"

    # next day Gelato changes the image (new fingerprint) → re-queue
    f2, r2, _ = _fakes(fingerprint="fpV2")
    s = ms.run_sync(stamp="T2", fetch_image=f2, rehost=r2, printarea=pa)
    assert s["requeued"] >= 1
    row = next(r for r in ms.review_rows() if r["product_id"] == pid)
    assert row["confirmed"] is False and row["review"] is None   # verdicts cleared
    # and confirm without fresh verdicts must NOT re-publish the new image
    ms.confirm(stamp="T2"); ms.publish(stamp="T2")
    # live still reflects only confirmed state (now unconfirmed → drops out)
    assert ms.live_mockups() == {}


def test_human_override_is_an_escape_hatch(cat_file, monkeypatch):
    _go_live(monkeypatch)
    fetch, rehost, pa = _fakes()
    ms.run_sync(stamp="T", fetch_image=fetch, rehost=rehost, printarea=pa)
    pid = next(r["product_id"] for r in ms.review_rows() if r["status"] == "ready")
    assert ms.override(pid, "approve", stamp="T") is True
    ms.publish(stamp="T")
    row = next(r for r in ms.review_rows() if r["product_id"] == pid)
    assert row["confirmed"] is True
    # by=human is recorded (not 'agents')
    data = json.loads(cat_file.read_text(encoding="utf-8"))
    assert data["products"][pid]["confirmed_by"] == "human"


# ── Future growth: enumeration is generic across all families ─────────────

def test_enumerates_all_product_families(cat_file):
    prods = ms.all_products()
    cats = {p["category"] for p in prods}
    assert {"mug", "branded", "calendar", "apparel"} <= cats
    assert len(prods) > 20                                    # the real catalog
    assert all(p.get("product_id") and p.get("sku") for p in prods)
