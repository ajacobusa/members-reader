"""Regression: the daily Gelato sync must surface placeholder product UIDs
loudly. A leftover placeholder (seed SKU) means orders silently fail to route,
so the sync result + text must flag it, and the admin command escalates when
live. Guards the 'missing real Gelato UID -> orders won't route' risk."""


def test_verify_catalog_detects_seed_placeholders():
    from quoteforge.etsy.gelato_catalog import verify_catalog_mappings
    m = verify_catalog_mappings()
    # The shipped seed catalog is all placeholders until the owner fills real UIDs.
    assert m["placeholder_count"] >= 1 and m["all_real"] is False
    assert all(p["current_sku"].upper().startswith("GEL-") or p["current_sku"] == "(empty)"
               for p in m["placeholders"])


def test_sync_result_reports_placeholder_uids():
    from quoteforge.automation.gelato_sync import sync_catalog
    r = sync_catalog()                       # TEST_MODE -> mock, still reports
    assert r["placeholder_uids"] >= 1
    assert isinstance(r["placeholders"], list) and r["placeholders"]


def test_sync_text_has_loud_banner_when_placeholders():
    from quoteforge.automation.gelato_sync import format_sync_text
    txt = format_sync_text({"checked": 22, "placeholder_uids": 2,
                            "placeholders": [{"product_id": "poster_8x10",
                                              "size": "8x10 in",
                                              "current_sku": "GEL-POSTER-8X10-STD"}]})
    low = txt.lower()
    assert "critical" in low and "fail to route" in low
    assert "poster_8x10" in txt


def test_sync_text_clean_when_all_real():
    from quoteforge.automation.gelato_sync import format_sync_text
    txt = format_sync_text({"checked": 22, "updated": 0, "discontinued": 0,
                            "message": "ok", "placeholder_uids": 0,
                            "placeholders": []})
    assert "CRITICAL" not in txt and "Gelato catalog sync" in txt
