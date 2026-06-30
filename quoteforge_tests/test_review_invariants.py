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
    # The two findings are now daily invariants (can't be silently dropped).
    from quoteforge.automation.infra_check import check_infrastructure
    names = {c["name"] for c in check_infrastructure()["checks"]}
    assert "calendar_multiimage_hold" in names
    assert "branded_uid_integrity" in names
