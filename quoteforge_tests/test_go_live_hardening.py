"""Go-live hardening for the three new departments (mugs / calendars / branded).

REGRESSION coverage for the risks found in the go-live audit: wrong print canvas,
calendars shipping cover-only, real costs not syncing, and mug/calendar shipping
under-modeled.
"""


def test_render_specs_per_department():
    # REGRESSION: mug/calendar/branded must render at their OWN canvas spec, not the
    # poster default (which would crop/stretch the print). The pipeline branches on
    # product_type to the per-department dimension helper.
    from quoteforge.etsy.mug_catalog import mug_dimensions_for
    from quoteforge.etsy.calendar_catalog import calendar_dimensions_for
    from quoteforge.etsy.gelato_catalog import dimensions_for
    poster = dimensions_for("18x24")
    mw, mh = mug_dimensions_for("classic_mug")
    cw, ch = calendar_dimensions_for("wall_cal")
    assert (mw, mh) != poster and (cw, ch) != poster
    assert mw > mh          # a mug wrap is a wide landscape panel
    assert ch > cw          # a wall calendar is a portrait page
    # each department's render-size helper is wired via the family registry, and the
    # pipeline resolves render size through it (regression lock - stronger than a name
    # check: it confirms the registry returns the SAME per-department spec).
    from quoteforge.etsy.families import family_for
    assert family_for("mug").render_size({"product_id": "classic_mug"}, "") == (mw, mh)
    assert family_for("calendar").render_size({"product_id": "wall_cal"}, "") == (cw, ch)
    assert family_for("branded") is not None
    import inspect
    import quoteforge.automation.pipeline_orchestrator as po
    assert "family_for" in inspect.getsource(po)


def test_route_order_holds_calendar_for_manual():
    # REGRESSION: a 12-month calendar must NEVER auto-submit as cover-only (the single
    # artwork_url path can't carry 12 month photos) - it is held for manual production.
    from quoteforge.fulfillment.router import route_order
    r = route_order(
        {"product_type": "calendar", "gelato_product_uid": "real-calendar-uid",
         "vendor": "gelato"},
        recipient={"name": "A B", "line1": "1 St", "city": "X",
                   "postcode": "10001", "country": "US"},
        artwork_url="http://example/cover.png")
    assert r["status"] == "manual"
    assert "calendar" in r["detail"].lower()


def test_gelato_sync_covers_all_departments():
    # REGRESSION: real Gelato costs/availability must sync for ALL departments, so the
    # margin guard compares against true cost (not the seed) - prevents under-floor.
    from quoteforge.automation.gelato_sync import _all_skus
    from quoteforge.etsy.mug_catalog import mug_skus
    from quoteforge.etsy.calendar_catalog import calendar_skus
    from quoteforge.etsy.branded_catalog import branded_skus
    allsk = set(_all_skus())
    assert set(mug_skus()) <= allsk
    assert set(calendar_skus()) <= allsk
    assert set(branded_skus()) <= allsk


def test_build_emits_nojekyll(tmp_path):
    # REGRESSION: GitHub Pages (legacy Jekyll, main /docs) FAILS to build the
    # generated storefront (braces / ${...}); the build must drop a .nojekyll next
    # to the page on EVERY rebuild so Pages serves the static site as-is. Without
    # this the live UAT silently freezes on the last good build.
    from PIL import Image
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    l = LAUNCH_PACK_20[0]
    g = tmp_path / f"{l.n:02d}_x" / "gallery"
    g.mkdir(parents=True)
    Image.new("RGB", (300, 300), (15, 61, 46)).save(g / "1_hero.png")
    from quoteforge.etsy.listing_preview import build_shop_home
    out = build_shop_home(numbers=[l.n], kit_dir=tmp_path,
                          out_path=tmp_path / "index.html")
    assert (out.parent / ".nojekyll").exists()


def test_shipping_models_mug_and_calendar_heavier_than_poster():
    # REGRESSION: mugs (heavy/fragile) and calendars (bulkier) must not fall back to
    # flat-poster shipping, or the variance tripwire never fires on their real cost.
    from quoteforge.etsy.shipping_audit import modeled_shipping
    base = modeled_shipping("US", "poster")
    assert modeled_shipping("US", "Classic Ceramic Mug (11oz) - White") > base
    assert modeled_shipping("US", "Wall Calendar - White") > base
