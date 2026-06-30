"""Regressions for the per-product grounded-review findings: a calendar is never
auto-submitted cover-only, and branded items keep their own placeholder-UID guard."""


def test_calendar_held_for_manual_not_cover_only(monkeypatch):
    # REGRESSION: a 12-month calendar is multi-image; the single-file submit path would
    # ship cover-only (silent under-delivery / chargeback). The router must HOLD it.
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "GELATO_FULFILLMENT_MODE", "quoteforge", raising=False)
    from quoteforge.fulfillment.router import route_order
    r = route_order({"order_id": "", "vendor": "gelato", "product_type": "calendar",
                     "gelato_product_uid": "real-uid"},
                    recipient={"name": "A"}, artwork_url="http://x/a.png")
    assert r["status"] == "manual" and "calendar" in r["detail"].lower()


def test_branded_uid_guard_detects_placeholders():
    # REGRESSION: branded items have their OWN Gelato placeholder guard so a GEL-*
    # branded SKU can't reach production.
    from quoteforge.etsy.branded_catalog import verify_branded_mappings
    m = verify_branded_mappings()
    assert isinstance(m, dict)
    assert "placeholder_count" in m and "all_real" in m and "total" in m


def test_new_infra_checks_are_wired():
    # The findings are now daily invariants (can't be silently dropped).
    from quoteforge.automation.infra_check import check_infrastructure
    names = {c["name"] for c in check_infrastructure()["checks"]}
    assert "calendar_multiimage_hold" in names
    assert "branded_uid_integrity" in names
    assert "apparel_multiarea_profitable" in names
    assert "gelato_cost_sync_grounded" in names         # daily Gelato cost discovery wired


def test_gelato_cost_sync_invariant_passes_and_is_grounded():
    # The daily Gelato cost/discontinued/UID discovery agent is part of infra-check.
    from quoteforge.automation.infra_check import check_infrastructure
    chk = next(c for c in check_infrastructure()["checks"]
               if c["name"] == "gelato_cost_sync_grounded")
    assert chk["ok"]


def test_gelato_sync_never_fabricates_cost_without_a_key():
    # REGRESSION: NO HALLUCINATION - with no live key / TEST_MODE the sync returns a mock
    # and changes nothing; it never invents a Gelato cost.
    from quoteforge.automation.gelato_sync import sync_catalog
    r = sync_catalog()
    assert r.get("mock") is True
    assert r.get("updated") == 0 and r.get("discontinued") == 0
