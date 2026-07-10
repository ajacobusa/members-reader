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
    assert {"create_from_template_injects_artwork",
            "stale_sweep_spares_store_product_rows",
            "mockup_sync_default_fetch_is_provenance",
            "create_with_artwork_aborts_on_fetch_failure"} <= names


# ── #185 outcome-audit findings, locked as regressions ─────────────────────

def test_store_product_rows_survive_daily_stale_sweep(tmp_path, monkeypatch):
    # REGRESSION (audit F1): rows persisted by create_product_with_artwork
    # (source='store_product') were retired by the next template-sync stale sweep
    # (unscoped last_seen_at cut), silently removing the official mockup from the
    # 'persisted' display path within a day.
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    from quoteforge.db import database as db
    db.init_db()
    assert db.upsert_product_image("GEL-M-TSHIRT-BLK-M", "https://cdn/mock1.png",
                                   gelato_product_uid="U-9", source="store_product")
    assert db.upsert_product_image("GEL-M-TSHIRT-BLK-M", "https://cdn/synced.png",
                                   gelato_product_uid="U-9", image_rank=5,
                                   source="gelato_ecommerce")
    db.deactivate_stale_product_images("9999-12-31 00:00:00")   # a later sweep
    rows = db.get_product_images("GEL-M-TSHIRT-BLK-M")
    assert [r["image_url"] for r in rows] == ["https://cdn/mock1.png"]
    # the synced-source row DID retire (the sweep still does its actual job)


def test_run_sync_default_fetch_preserves_provenance(tmp_path, monkeypatch):
    # REGRESSION (audit F2): the production mockup-sync (admin path, no fetch_image
    # arg) used the bare-URL fetcher, so an unverified-origin image was rebound to
    # the SKU's real UID "by construction" and the confirm() provenance gate could
    # never hold anything.
    from quoteforge.automation import mockup_sync as ms
    from quoteforge.images import supplier_mockup as sm
    saved = {}
    monkeypatch.setattr(ms, "load_catalog", lambda: {"products": {}})
    monkeypatch.setattr(ms, "save_catalog", lambda cat, stamp=None: saved.update(cat))
    monkeypatch.setattr(ms, "all_products",
                        lambda: [{"product_id": "p1", "sku": "SKU1",
                                  "category": "tshirt", "name": "Tee"}])
    monkeypatch.setattr(ms, "_real_uid", lambda sku: "real-uid-1")
    monkeypatch.setattr(ms, "_live_gated", lambda: True)
    prov = {"url": "https://cdn/x.png", "uid": None, "source": "persisted"}
    monkeypatch.setattr(sm, "gelato_blank_image_provenance",
                        lambda sku, refresh=False: dict(prov))
    img = tmp_path / "x.jpg"
    img.write_bytes(b"j")
    ms.run_sync(stamp="2026-01-01T00:00:00Z",
                rehost=lambda url, pid: (str(img), "fp"),
                printarea=lambda uid: None)
    fetched = saved["products"]["p1"]["checkpoints"]["fetched"]
    assert fetched["resolved_uid"] is None      # unverified stays unverified -> held
    assert fetched["source"] == "persisted"


def test_rerun_same_sku_is_idempotent_and_never_shows_stale(tmp_path, monkeypatch):
    # REGRESSION (audit F3): a re-run created a SECOND live vendor product and left
    # the OLD product's rows active at rank 0, so the 'persisted' pick stayed stale.
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    from quoteforge.db import database as db
    db.init_db()

    def seams(pid, url):
        return dict(template_getter=lambda tid: TPL,
                    creator=lambda v: {"id": pid},
                    product_getter=lambda _p: {"previewUrl": url})
    glo.create_product_with_artwork("T1", "Tee", "https://art/a.png", sku="SKU1",
                                    **seams("SP-1", "https://cdn/old.png"))
    res2 = glo.create_product_with_artwork("T1", "Tee", "https://art/b.png",
                                           sku="SKU1",
                                           **seams("SP-2", "https://cdn/new.png"))
    assert "skipped" in res2                       # no duplicate vendor create
    res3 = glo.create_product_with_artwork("T1", "Tee", "https://art/b.png",
                                           sku="SKU1", force=True,
                                           **seams("SP-2", "https://cdn/new.png"))
    assert res3["created"] is True
    rows = db.get_product_images("SKU1")
    assert [r["image_url"] for r in rows] == ["https://cdn/new.png"]  # old retired


def test_persisted_uid_is_variant_product_uid_not_store_id(tmp_path, monkeypatch):
    # REGRESSION (audit F4): rows recorded the STORE-PRODUCT id in
    # gelato_product_uid, so the provenance gate (origin uid == real uid) could
    # never legitimately pass once provenance is honest.
    monkeypatch.setattr("quoteforge.db.database.DB_PATH", tmp_path / "t.db")
    from quoteforge.db import database as db
    db.init_db()
    glo.create_product_with_artwork(
        "T1", "Tee", "https://art/a.png", sku="SKU1",
        template_getter=lambda tid: TPL, creator=lambda v: {"id": "SP-9"},
        product_getter=lambda pid: {"previewUrl": "https://cdn/m.png",
                                    "variants": [{"productUid": "real-uid-9"}]})
    rows = db.get_product_images("SKU1")
    assert rows and rows[0]["gelato_product_uid"] == "real-uid-9"   # not "SP-9"


def test_template_fetch_failure_aborts_create():
    # REGRESSION (audit F5): a transient template-fetch error fell through to
    # variants=[] and STILL created a live store product WITHOUT our artwork.
    calls = []

    def boom(tid):
        raise RuntimeError("network blip")
    res = glo.create_product_with_artwork(
        "T1", "Tee", "https://art/design.png", template_getter=boom,
        creator=lambda v: calls.append(v) or {"id": "SP-X"},
        product_getter=lambda pid: {})
    assert calls == []
    assert res.get("created") is False and "template fetch" in res.get("reason", "")


def test_no_sku_persist_skip_is_reported():
    # REGRESSION (audit F6): an empty/whitespace sku silently skipped persistence.
    res = glo.create_product_with_artwork(
        "T1", "Tee", "https://art/a.png", sku="   ",
        template_getter=lambda tid: TPL, creator=lambda v: {"id": "SP-1"},
        product_getter=lambda pid: {"previewUrl": "https://cdn/m.png"})
    assert res["created"] is True and res["persist_skipped"] == "no sku"


def test_mockup_urls_key_parity_with_trusted_extractor():
    # REGRESSION (audit F7): a product exposing only mockupUrl / productImageUrl /
    # image yielded [] -> saved_images=0 silently.
    assert glo._mockup_urls({"mockupUrl": "https://cdn/a.png",
                             "productImageUrl": "https://cdn/b.png",
                             "image": "https://cdn/c.png"}) == [
        "https://cdn/a.png", "https://cdn/b.png", "https://cdn/c.png"]


def test_invariants_are_comment_immune():
    # REGRESSION (audit F8): invariant legs were raw substring matches a comment
    # could satisfy; the AST helpers must reject comment-only decoys.
    from quoteforge.automation.infra_check import _references, _uses_string
    from quoteforge.db import database as db

    def decoy(sku):
        # upsert_product_image(sku, u)      <- comment only: must NOT count
        # source != 'store_product'         <- comment only: must NOT count
        return {"created": True}
    assert not _references(decoy, "upsert_product_image")
    assert not _uses_string(decoy, "source != 'store_product'")
    assert _references(glo.create_product_with_artwork, "upsert_product_image")
    assert _references(glo.create_product_with_artwork, "deactivate_product_images")
    assert _uses_string(db.deactivate_stale_product_images,
                        "source != 'store_product'")
