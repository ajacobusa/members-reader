"""Scheduled Gelato catalog-review agent (network injected for tests)."""


def test_review_flags_discontinued_and_new_lines():
    from quoteforge.automation.gelato_catalog_review import review_catalog
    fam = {"mug:classic_mug": "mug_alive", "branded:tote": "tote_gone"}
    res = review_catalog(
        check_uid=lambda uid: uid != "tote_gone",          # tote discontinued
        list_catalogs=lambda: ["mugs", "tote-bags", "NEW-LINE"],
        count_catalog=lambda c: {"mugs": 10}.get(c, 1),
        family_map=fam,
        prev_snapshot={"catalogs": ["mugs", "tote-bags"], "counts": {"mugs": 8}})
    assert res["summary"]["discontinued"] == 1
    assert res["discontinued"][0]["family"] == "branded:tote"
    assert "NEW-LINE" in res["new_catalogs"]
    assert res["count_changes"].get("mugs", {}).get("delta") == 2


def test_review_clean_when_in_sync():
    from quoteforge.automation.gelato_catalog_review import review_catalog
    res = review_catalog(lambda u: True, lambda: ["mugs"], lambda c: 5,
                         {"mug:classic_mug": "u1"},
                         {"catalogs": ["mugs"], "counts": {"mugs": 5}})
    assert res["summary"]["discontinued"] == 0
    assert not res["new_catalogs"] and not res["removed_catalogs"]
    assert "in sync" in __import__("quoteforge.automation.gelato_catalog_review",
                                   fromlist=["format_review"]).format_review(res)


def test_review_network_blip_never_false_flags_discontinued():
    from quoteforge.automation.gelato_catalog_review import review_catalog

    def boom(uid):
        raise RuntimeError("network down")

    res = review_catalog(boom, lambda: [], lambda c: 0, {"a:b": "u1"}, {})
    # a transient failure must NOT report a live product as discontinued
    assert res["summary"]["discontinued"] == 0


def test_review_reports_only_never_mutates_map():
    # The agent returns a report + snapshot; the input family_map is untouched.
    from quoteforge.automation.gelato_catalog_review import review_catalog
    fam = {"mug:classic_mug": "u1"}
    review_catalog(lambda u: True, lambda: [], lambda c: 1, fam, {})
    assert fam == {"mug:classic_mug": "u1"}
