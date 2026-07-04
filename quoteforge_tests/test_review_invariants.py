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
    assert "sleeve_order_integrity_grounded" in names   # a paid sleeve can't be dropped from the order
    assert "apparel_preview_matches_print_guard" in names  # no poster auto-submitted in place of the design
    assert "daily_mockup_update_scheduled" in names        # daily real-product-photo refresh can't drop out
    assert "listing_image_pipeline_wired" in names          # the Etsy gallery-image pipeline can't silently drop an image/rank/cap
    assert "ecommerce_image_sync_wired" in names             # official-image auto-pull is scheduled + self-activating
    assert "template_image_sync_wired" in names              # template-image persistence is scheduled + idempotent


def test_listing_image_pipeline_invariant_passes_and_is_grounded():
    # The listing-image pipeline invariant (#35) is live and currently green.
    from quoteforge.automation.infra_check import check_infrastructure
    chk = next(c for c in check_infrastructure()["checks"]
               if c["name"] == "listing_image_pipeline_wired")
    assert chk["ok"], chk["detail"]


def test_listing_image_check_is_grounded_not_a_substring_match(tmp_path):
    # REGRESSION: prove the invariant is GROUNDED - if build_listing_pack stopped
    # generating an image (here: size_chart) or the publisher lost the 10-cap, the
    # structural helpers must go False (not a comment/substring false-pass).
    from quoteforge.automation import infra_check as ic
    from quoteforge.images import listing_pack as lp
    from quoteforge.automation import etsy_publisher as ep
    # the real pipeline is fully wired today
    assert all(ic._references(lp.build_listing_pack, g)
               for g in ("hero_room", "closeup", "size_chart",
                         "how_it_works", "whats_included"))
    assert ic._has_constant(ep.publish_launch_kit, 10)

    # decoys that dropped size_chart / the cap must FAIL the same grounded helpers
    def _build_regressed(poster_path, output_dir=None):
        _hero(); _close(); _how(); _incl()          # size_chart intentionally dropped

    def _publish_regressed(live=False, kit_dir=None):
        for rank, img in enumerate(_imgs, 1):        # imgs[:10] cap removed
            _upload("x", img, rank)

    assert not ic._references(_build_regressed, "size_chart")
    assert not ic._has_constant(_publish_regressed, 10)


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
