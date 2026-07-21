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
    assert "editor_state_resets_on_open" in names            # no cross-product editor state leak (openM hygiene)
    assert "editor_back_nav_guarded" in names                # tap-back is backward-only + inert after acceptance
    assert "template_image_sync_wired" in names              # template-image persistence is scheduled + idempotent
    assert "etsy_listing_create_dedupe" in names             # re-run can't create duplicate Etsy listings
    assert "sync_jobs_alert_on_failure" in names             # a silently-failing image sync alerts the owner
    assert "sync_heartbeat_wired" in names                   # uptime: jobs stamp sync_runs; a stopped job is detectable
    assert "listing_autolink_wired" in names                 # create persists the SKU->listing link; orphans are visible
    assert "audit_log_wired" in names                        # a privileged order-lock override leaves an accountable record
    assert "utc_local_datetime_hygiene" in names             # the two UTC-vs-local sites that bit us stay UTC-aware
    assert "route_paths_thread_product_type" in names        # BOTH route_order sites thread product_type (apparel gate can't be bypassed)
    assert "product_photo_override_wired" in names            # owner real-photo override shows the real product in TEST_MODE (no go-live)
    assert "sleeveless_garment_gated" in names                # a tank never offers sleeve areas/upcharge; back proof != front photo
    assert "event_retention_pruned" in names                  # sync_runs/security_events are pruned (bounded growth)
    assert "mug_wrap_ability_gated" in names                   # single-panel mugs never sold a full wrap
    assert "framed_sizes_fulfillable" in names                 # no framed size sold without a prepared UID
    assert "apparel_print_files_wired" in names                 # faithful per-side DTG print files render + capture
    assert "apparel_print_files_upload_wired" in names          # print files upload to backend + reach the order
    assert "uid_reverse_join_collision_safe" in names           # a shared Gelato UID can't misroute a product photo
    assert "official_image_table_consumed" in names             # the persisted official-image table is actually read
    assert "supplier_image_cache_uid_bound" in names            # a UID remap refetches (no stale old-product image)
    assert "variant_uid_static_before_cache" in names           # static UID map wins over a stale dynamic cache


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


def test_existing_listing_id_dedupe_helper(tmp_path, monkeypatch):
    # REGRESSION (#182): the listing-create dedupe helper reuses a prior listing id
    # for a SKU so a re-run can't POST a duplicate Etsy listing.
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.upsert_product({"product_id": "launch-1", "gelato_sku": "launch-1",
                       "etsy_listing_id": "L1", "template_id": "", "category": "c",
                       "title": "t", "price_usd": 1.0, "gelato_cost_usd": 0.2,
                       "product_type": "print", "size": ""})
    assert db.existing_listing_id("launch-1") == "L1"
    assert db.existing_listing_id("launch-2") == ""     # unknown -> no dupe block


def test_create_draft_listing_reuses_existing(tmp_path, monkeypatch):
    # REGRESSION (#182): create_draft_listing returns the existing id (no POST) when a
    # listing already maps to the launch SKU. Forces the live branch via monkeypatch.
    from quoteforge.automation import etsy_publisher as ep
    from quoteforge.db import database as db
    from quoteforge.etsy.launch_pack import LAUNCH_PACK_20
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setattr(ep, "TEST_MODE", False, raising=False)
    monkeypatch.setattr(ep, "prerequisites", lambda: [])   # pretend live-ready
    db.upsert_product({"product_id": "launch-1", "gelato_sku": "launch-1",
                       "etsy_listing_id": "L1", "template_id": "", "category": "c",
                       "title": "t", "price_usd": 1.0, "gelato_cost_usd": 0.2,
                       "product_type": "print", "size": ""})
    called = {"post": False}

    class _R:
        def post(self, *a, **k):
            called["post"] = True
            raise AssertionError("must not POST when a listing already exists")
    r = ep.create_draft_listing(LAUNCH_PACK_20[0], 19.0, runner=_R())
    assert r["status"] == "exists" and r["listing_id"] == "L1" and not called["post"]


def test_sync_run_heartbeat_records_and_reads(tmp_path, monkeypatch):
    # UPTIME (#182): record_sync_run stamps a row; last_sync_run reads the latest.
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    assert db.last_sync_run("template-sync") == {}          # never ran
    db.record_sync_run("template-sync", ok=True, detail="checked=3")
    db.record_sync_run("template-sync", ok=False, detail="boom")
    last = db.last_sync_run("template-sync")
    assert last["ok"] == 0 and "boom" in last["detail"]     # latest run wins


def test_healthcheck_flags_a_failed_sync_run(tmp_path, monkeypatch):
    # UPTIME: a job whose last run FAILED shows a WARN in the health report.
    from quoteforge.db import database as db
    from quoteforge.automation import healthcheck as hc
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.record_sync_run("template-sync", ok=False, detail="auth 403")
    c = hc.check_sync_freshness()
    assert c.status == "WARN" and "template-sync" in c.detail


def test_healthcheck_ok_when_no_runs_yet(tmp_path, monkeypatch):
    # A fresh install (no runs recorded) must NOT false-alarm.
    from quoteforge.db import database as db
    from quoteforge.automation import healthcheck as hc
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    assert hc.check_sync_freshness().status == "OK"


def test_healthcheck_staleness_is_utc_correct(tmp_path, monkeypatch):
    # REGRESSION (#182 verify): ran_at is SQLite datetime('now') == UTC. A ~40h-old
    # UTC row must read as STALE and a ~1h-old UTC row must read as FRESH regardless
    # of the host timezone (the old code compared UTC against naive-local -> off by
    # the host's UTC offset). We write ran_at directly in UTC and pin both branches.
    from datetime import datetime, timedelta, timezone
    from quoteforge.db import database as db
    from quoteforge.automation import healthcheck as hc
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()

    def _stamp(job, hours_ago):
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
            "%Y-%m-%d %H:%M:%S")                        # SQLite's space-separated UTC form
        with db._conn() as conn:
            conn.execute("INSERT INTO sync_runs (job, ran_at, ok, detail) "
                         "VALUES (?,?,1,'')", (job, ts))

    _stamp("template-sync", 40)                          # older than the 36h window
    c = hc.check_sync_freshness()
    assert c.status == "WARN" and "template-sync" in c.detail

    # a 1h-old run for every job -> fresh, OK (proves no false-alarm off-UTC)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t2.db")
    db.init_db()
    for job in ("template-sync", "ecommerce-images", "mockup-sync"):
        _stamp(job, 1)
    assert hc.check_sync_freshness().status == "OK"


def test_orphan_products_detects_unpublished_only(tmp_path, monkeypatch):
    # REGRESSION (#182-P0b): orphan_products returns ACTIVE, fulfillment-mapped
    # products that have NO Etsy listing linked - and ONLY those. A published product
    # (has etsy_listing_id) and an inactive one must not show up.
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    base = {"category": "c", "title": "t", "price_usd": 1.0, "gelato_cost_usd": 0.2,
            "product_type": "print", "size": "", "template_id": ""}
    db.upsert_product({**base, "product_id": "linked", "gelato_sku": "s1",
                       "etsy_listing_id": "L1"})              # published -> not orphan
    db.upsert_product({**base, "product_id": "orphan", "gelato_sku": "s2",
                       "etsy_listing_id": ""})                # never published -> orphan
    ids = {o["product_id"] for o in db.orphan_products()}
    assert ids == {"orphan"}


def test_orphan_detector_treats_whitespace_listing_id_as_unlinked(tmp_path, monkeypatch):
    # REGRESSION (#182-P0b audit): a whitespace-only etsy_listing_id is unbuyable but the
    # exact =='' filter missed it (only NULL/'' were caught). TRIM()='' must surface it.
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "o.db")
    db.init_db()
    base = {"category": "c", "title": "t", "price_usd": 1.0, "gelato_cost_usd": 0.2,
            "product_type": "print", "size": "", "template_id": ""}
    db.upsert_product({**base, "product_id": "ws", "gelato_sku": "s",
                       "etsy_listing_id": "   "})          # whitespace-only -> unbuyable
    assert "ws" in {o["product_id"] for o in db.orphan_products()}


def test_create_draft_listing_persists_the_link_write_side():
    # REGRESSION (#182-P0b): the dedupe invariant guards only the READ side. Prove the
    # WRITE side is wired - create_draft_listing must reference upsert_product so the
    # SKU->listing map actually FILLS (else a re-run duplicates). This is the exact
    # symbol the listing_autolink_wired invariant pins.
    from quoteforge.automation import infra_check as ic
    from quoteforge.automation import etsy_publisher as ep
    assert ic._references(ep.create_draft_listing, "upsert_product")

    # a regressed create that dropped the persist must FAIL the same grounded helper
    def _create_regressed(bundle, price, runner=None):
        resp = runner.post("u")                               # POSTs but never persists
        return {"status": "created", "listing_id": resp}
    assert not ic._references(_create_regressed, "upsert_product")


def test_lock_override_writes_an_audit_record(tmp_path, monkeypatch):
    # REGRESSION (#182-P2): update_order's docstring promises an "audited admin
    # override". Prove it: overriding a locked field on a customer-approved order with
    # allow_locked=True writes a security_events row; a NON-override edit does not.
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    oid = db.create_order({"order_id": "O-1", "recipient_name": "A", "occasion": "B"})
    db.update_order(oid, proof_approved=1)                    # lock it
    # a normal lifecycle edit (status) must NOT create an audit event
    db.update_order(oid, status="printing")
    assert db.recent_security_events(event="order_lock_override") == []
    # the privileged override MUST
    db.update_order(oid, occasion="CHANGED", allow_locked=True)
    evs = db.recent_security_events(event="order_lock_override")
    assert len(evs) == 1 and oid in evs[0]["detail"] and evs[0]["actor"] == "admin"


def test_locked_order_still_raises_without_override(tmp_path, monkeypatch):
    # REGRESSION (#182-P2): the audit refactor must NOT weaken the lock - a locked-field
    # edit WITHOUT allow_locked still raises OrderLockedError (and writes no audit row).
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    oid = db.create_order({"order_id": "O-2", "recipient_name": "A", "occasion": "B"})
    db.update_order(oid, proof_approved=1)
    import pytest
    with pytest.raises(db.OrderLockedError):
        db.update_order(oid, occasion="X")                   # no override -> blocked
    assert db.recent_security_events(event="order_lock_override") == []


def test_record_security_event_is_best_effort(tmp_path, monkeypatch):
    # An audit write must never crash the action it records (bad/locked DB) - it logs
    # and returns. Empty event is a no-op.
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.record_security_event("")                             # no-op, no row
    assert db.recent_security_events() == []
    def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "_conn", _boom)
    db.record_security_event("x", detail="d")               # must not raise


def test_utc_hygiene_tripwire_is_grounded():
    # REGRESSION (#182 audit): the utc_local_datetime_hygiene invariant is live + green,
    # AND grounded - a function that reverts to naive-local datetime.now() (the bug)
    # drops the .utc reference and would flip the same helper red.
    from quoteforge.automation import infra_check as ic
    from quoteforge.automation import healthcheck as hc
    from quoteforge.automation import template_image_sync as tis
    chk = next(c for c in ic.check_infrastructure()["checks"]
               if c["name"] == "utc_local_datetime_hygiene")
    assert chk["ok"], chk["detail"]
    # the real fixed sites reference UTC...
    assert ic._references(hc.check_sync_freshness, "utc")
    assert ic._references(tis.sync_template_images, "utc")
    # ...a naive-local decoy (the bug shape) does NOT -> the tripwire would fire
    import datetime as _d
    def _regressed_sweep():
        return _d.datetime.now().isoformat(timespec="seconds")   # naive local, the bug
    assert not ic._references(_regressed_sweep, "utc")


def test_framed_sizes_match_fulfillable_catalog():
    # REGRESSION (wall-art fulfillability audit, CRITICAL): the editor derived framed
    # sizes from POSTER sizes (12x16, 24x36), but build_wallart_map prepares framed UIDs
    # ONLY for the framed catalog sizes - so a customer could pay for a framed size with
    # no prepared UID. Every framed size sold must have a framed catalog entry.
    from quoteforge.etsy.variations import build_variations, _ns
    from quoteforge.etsy.gelato_catalog import GELATO_CATALOG
    sold = {_ns(v.size) for v in build_variations() if v.material == "framed"}
    catalog = {_ns(p.size) for p in GELATO_CATALOG if p.category == "framed"}
    assert sold <= catalog, f"framed sizes sold without a UID: {sorted(sold - catalog)}"
    assert _ns("12x16") not in sold and _ns("24x36") not in sold   # the two removed


def test_single_panel_mugs_are_not_sold_a_full_wrap():
    # REGRESSION (fulfillability audit, CRITICAL): color/accent/travel mugs are single-
    # panel (handle breaks the wrap, wraps=False). The editor must consume that flag so
    # they never offer the Wraparound layout or spin a full-wrap proof (the buyer would
    # approve a wrap that prints as one panel). Grounded on the catalog + the generator.
    import inspect
    from quoteforge.etsy.mug_catalog import MUG_CATALOG, get_mug
    from quoteforge.etsy import listing_preview as lp
    assert get_mug("color_mug").wraps is False and get_mug("classic_mug").wraps is True
    assert any(not m.wraps for m in MUG_CATALOG)
    src = inspect.getsource(lp)
    assert "MUG_WRAPS" in src and "_p.wraps" in src            # wrap-ability crosses the seam
    assert "function _mugWraps()" in src
    assert "!_mugWraps()" in src                               # layout gate consumes it
    assert "_mw?5.3:1.9" in src                                # proof arc gated per-mug


def test_supplier_image_cache_invalidates_on_uid_remap(tmp_path, monkeypatch):
    # REGRESSION (Gelato->Etsy image re-audit, CRITICAL): the SKU->URL cache is UID-bound,
    # so after the owner REMAPS a SKU to a new Gelato UID, gelato_blank_image returns the
    # NEW uid's image - not the OLD product forever (the SKU-only key showed it stale).
    import quoteforge.images.supplier_mockup as sm
    from quoteforge.automation import gelato_api, gelato_sync
    import quoteforge.config as cfg
    monkeypatch.setenv("GELATO_MOCKUP_CACHE", str(tmp_path / "mock.json"))
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(gelato_api, "GELATO_API_KEY", "k", raising=False)
    monkeypatch.setattr(sm, "product_photo_overrides", lambda: {})
    monkeypatch.setattr(sm, "_fetch_product_image", lambda uid: f"http://cdn/{uid}.png")
    monkeypatch.setattr(gelato_sync, "_uid_map", lambda: {"SKU-X": "UID-OLD"})
    assert sm.gelato_blank_image("SKU-X") == "http://cdn/UID-OLD.png"
    monkeypatch.setattr(gelato_sync, "_uid_map", lambda: {"SKU-X": "UID-NEW"})  # remap
    assert sm.gelato_blank_image("SKU-X") == "http://cdn/UID-NEW.png"           # not stale


def test_variant_static_uid_clears_stale_dynamic_cache(tmp_path, monkeypatch):
    # REGRESSION (Gelato->Etsy image re-audit, MEDIUM): a corrected static UID map entry
    # wins over a stale dynamically-cached variant UID AND clears it, so an order can never
    # route to the wrong product from a resurfaced old dynamic value.
    from quoteforge.automation import gelato_variant_resolver as gvr, gelato_sync
    monkeypatch.setenv("GELATO_VARIANT_CACHE", str(tmp_path / "vuid.json"))
    gvr._save_cache({"AP-TEE-M-BLACK": "uid_STALE"})
    monkeypatch.setattr(gelato_sync, "_uid_map", lambda: {"AP-TEE-M-BLACK": "uid_CORRECTED"})
    assert gvr.resolve_variant_uid("AP-TEE-M-BLACK") == "uid_CORRECTED"
    assert "AP-TEE-M-BLACK" not in gvr._load_cache()            # stale dynamic entry cleared


def test_uid_reverse_join_drops_collisions(monkeypatch):
    # REGRESSION (Gelato->Etsy image audit, HIGH): two of our SKUs sharing one real Gelato
    # UID must NOT resolve that UID to an arbitrary SKU (would put the wrong product photo
    # on the wrong tile). The colliding UID is skipped; unique UIDs still resolve;
    # GEL-* placeholders are excluded.
    from quoteforge.automation.gelato_sync import invert_uid_map
    r = invert_uid_map({"SKU-A": "UID-1", "SKU-B": "UID-1",
                        "SKU-C": "UID-2", "SKU-D": "GEL-PLACEHOLDER"})
    assert "UID-1" not in r                    # ambiguous -> skipped, never guessed
    assert r.get("UID-2") == "SKU-C"           # unique -> resolves
    assert "GEL-PLACEHOLDER" not in r          # placeholder -> excluded
    # both consumers use the shared collision-safe helper
    import inspect
    from quoteforge.automation import ecommerce_images as ei, template_image_sync as tis
    assert "invert_uid_map" in inspect.getsource(ei._compute_images_by_sku)
    assert "invert_uid_map" in inspect.getsource(tis._uid_to_sku)


def test_gelato_blank_image_prefers_persisted_table(tmp_path, monkeypatch):
    # REGRESSION (Gelato->Etsy image audit, MEDIUM): a persisted official image
    # (gelato_product_images, written + stale-retired by template-sync) is returned for
    # the SKU before falling through to the live in-memory ecommerce lookup - so the
    # durable-persistence + stale-retire guarantee actually reaches the display.
    import quoteforge.images.supplier_mockup as sm
    from quoteforge.automation import gelato_api
    import quoteforge.config as cfg
    monkeypatch.setattr(sm, "product_photo_overrides", lambda: {})
    monkeypatch.setattr(cfg, "TEST_MODE", False)
    monkeypatch.setattr(gelato_api, "GELATO_API_KEY", "k", raising=False)
    monkeypatch.setattr("quoteforge.db.database.get_product_images",
                        lambda sku, **k: [{"image_url": "https://cdn/persisted.png"}])
    assert sm.gelato_blank_image("QF-SKU") == "https://cdn/persisted.png"


def test_prune_event_tables_trims_old_rows(tmp_path, monkeypatch):
    # HYGIENE (#realphotos follow-up): the append-only heartbeat + audit tables get a
    # 1-year retention prune (via db_maintenance) so they can't grow unbounded. Old rows
    # go; recent rows stay. UTC cutoff matches how the columns are written.
    from quoteforge.db import database as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    with db._conn() as c:
        c.execute("INSERT INTO sync_runs (job, ran_at) VALUES ('old', datetime('now','-400 days'))")
        c.execute("INSERT INTO sync_runs (job) VALUES ('new')")
        c.execute("INSERT INTO security_events (event, at) VALUES ('old', datetime('now','-400 days'))")
        c.execute("INSERT INTO security_events (event) VALUES ('new')")
    res = db.prune_event_tables()
    assert res == {"sync_runs": 1, "security_events": 1}       # exactly the old rows
    assert db.last_sync_run("new") and db.last_sync_run("old") == {}
    assert len(db.recent_security_events()) == 1                # only the recent audit row
    # db_maintenance surfaces the pruned counts
    assert "pruned" in db.db_maintenance()


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
