"""#185: create-from-template with OUR artwork injected into image placeholders.

The spec this pins (QuoteForge -> Gelato -> official mockup -> DB -> storefront):
artwork URL goes into the documented ``variants[].imagePlaceholders[].fileUrl``
block (never guessed placeholder names - they come from the fetched template),
the created product's official mockup URLs are extracted and persisted into
``gelato_product_images`` (the 'persisted' display source the gatekeeper pipeline
reads), and everything stays a defensive no-op off-live. All IO injected.
"""
from quoteforge.automation import gelato_live_ops as glo


TPL = {"id": "T1", "variants": [
    {"id": "V1", "imagePlaceholders": [{"name": "front"}, {"name": "back"}]},
    {"id": "V2", "imagePlaceholders": [{"name": "front"}]},
    {"id": "V3"},                                # no placeholders -> skipped
]}


def test_artwork_variants_builds_documented_payload():
    v = glo._artwork_variants(TPL, "https://art/design.png")
    assert v == [
        {"imagePlaceholders": [{"name": "front", "fileUrl": "https://art/design.png"},
                               {"name": "back", "fileUrl": "https://art/design.png"}],
         "templateVariantId": "V1"},
        {"imagePlaceholders": [{"name": "front", "fileUrl": "https://art/design.png"}],
         "templateVariantId": "V2"},
    ]
    # never invents placeholders: empty/odd template -> [] (template layers kept)
    assert glo._artwork_variants({}, "https://art/x.png") == []
    assert glo._artwork_variants(TPL, "") == []


def test_full_chain_persists_official_mockups(tmp_path, monkeypatch):
    # REGRESSION (#185): create with artwork -> extract mockup URLs -> persist rows
    # readable by get_product_images (the 'persisted' customer-display source).
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    from quoteforge.db import database as db
    db.init_db()
    sent = {}

    def creator(variants):
        sent["variants"] = variants
        return {"id": "SP-9"}

    def product_getter(pid):
        assert pid == "SP-9"
        return {"previewUrl": "https://cdn/mock1.png",
                "images": [{"url": "https://cdn/mock2.png"},
                           {"url": "https://cdn/mock1.png"}]}   # dupe -> deduped

    res = glo.create_product_with_artwork(
        "T1", "Custom Tee", "https://art/design.png", sku="GEL-M-TSHIRT-BLK-M",
        template_getter=lambda tid: TPL, creator=creator,
        product_getter=product_getter)
    assert res["created"] is True and res["artwork_injected"] is True
    assert sent["variants"][0]["imagePlaceholders"][0]["fileUrl"] == "https://art/design.png"
    assert res["mockup_urls"] == ["https://cdn/mock1.png", "https://cdn/mock2.png"]
    assert res["saved_images"] == 2
    rows = db.get_product_images("GEL-M-TSHIRT-BLK-M")
    assert [r["image_url"] for r in rows][:2] == ["https://cdn/mock1.png",
                                                  "https://cdn/mock2.png"]
    assert all(r["source"] == "store_product" for r in rows)


def test_create_failure_reported_never_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    from quoteforge.db import database as db
    db.init_db()
    res = glo.create_product_with_artwork(
        "T1", "Custom Tee", "https://art/design.png", sku="GEL-X",
        template_getter=lambda tid: TPL, creator=lambda v: {},   # provider failure
        product_getter=lambda pid: {})
    assert res["created"] is False and "no product id" in res["reason"]
    assert db.get_product_images("GEL-X") == []


def test_offline_is_a_safe_noop():
    # TEST_MODE / no key -> {skipped}, no IO attempted (no injected seams needed).
    res = glo.create_product_with_artwork("T1", "X", "https://art/x.png")
    assert "skipped" in res


def test_cli_and_invariant_registered():
    from quoteforge.admin import COMMANDS
    import inspect
    assert "create-with-artwork" in inspect.getsource(COMMANDS["gelato-live"])
    from quoteforge.automation.infra_check import check_infrastructure
    names = {c["name"] for c in check_infrastructure()["checks"]}
    assert "create_from_template_injects_artwork" in names
