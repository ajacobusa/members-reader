"""Template-image sync (#181): idempotent persistence, safe no-op, self-diagnosing.

The connected store has 0 products today, so live behaviour is mocked; these prove
the persistence + gating + join LOGIC (never a duplicate image, never a wrong map)."""
import quoteforge.automation.template_image_sync as ts
import quoteforge.automation.ecommerce_images as ei
from quoteforge.db import database as db


def _isolate_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db", raising=False)
    db.init_db()


def _go_live(monkeypatch, store="store-1"):
    import quoteforge.config as cfg
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(cfg, "TEST_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "GELATO_STORE_ID", store, raising=False)
    monkeypatch.setattr(ga, "GELATO_API_KEY", "test-key", raising=False)
    ei._IMG_CACHE = None


# ── DB idempotency ──────────────────────────────────────────────

def test_product_image_upsert_is_idempotent(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    db.upsert_product_image("SKU-A", "https://x/1.png", gelato_product_uid="U1")
    db.upsert_product_image("SKU-A", "https://x/2.png", gelato_product_uid="U1")  # same key
    rows = db.get_product_images("SKU-A")
    assert len(rows) == 1 and rows[0]["image_url"] == "https://x/2.png"


def test_upsert_ignores_empty_sku_or_url(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    assert db.upsert_product_image("", "https://x.png") == 0
    assert db.upsert_product_image("SKU", "") == 0
    assert db.get_product_images() == []


def test_deactivate_stale_retires_old_rows(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    db.upsert_product_image("SKU-A", "https://x/1.png")
    # a future stamp -> the row is "stale" relative to it -> retired
    n = db.deactivate_stale_product_images("2999-01-01T00:00:00")
    assert n == 1
    assert db.get_product_images("SKU-A", active_only=True) == []
    assert len(db.get_product_images("SKU-A", active_only=False)) == 1


# ── Sync gating + persistence ───────────────────────────────────

def test_sync_is_safe_noop_in_test_mode(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    r = ts.sync_template_images()
    assert r["enabled"] is False and r["upserted"] == 0 and r["failed"] == []


def test_sync_persists_mapped_products(tmp_path, monkeypatch):
    # REGRESSION: the stale-sweep cutoff must match how last_seen_at is written
    # (SQLite datetime('now') == UTC, space-separated). A naive-local / 'T'-separated
    # stamp string-compares wrong once local-date == UTC-date and RETIRES the row the
    # same run just wrote -> the storefront silently loses its official photos. This
    # asserts the freshly-synced row SURVIVES its own run's sweep (retired == 0),
    # deterministically at any host timezone / time of day.
    _isolate_db(monkeypatch, tmp_path)
    _go_live(monkeypatch)
    # one product carrying our SKU as externalId, with a resolvable image
    monkeypatch.setattr(ei, "store_products",
                        lambda: [{"id": "p1", "externalId": "GEL-MUG"}])
    monkeypatch.setattr(ts, "_images_of",
                        lambda p: [{"url": "https://s3/mug.jpg", "uid": "u", "type": "mockup"}])
    r = ts.sync_template_images()
    assert r["enabled"] is True and r["checked"] == 1 and r["upserted"] == 1
    assert r["retired"] == 0                          # fresh row must NOT be swept
    rows = db.get_product_images("GEL-MUG")
    assert len(rows) == 1 and rows[0]["image_url"] == "https://s3/mug.jpg"


def test_sync_skips_ambiguous_products(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    _go_live(monkeypatch)
    import quoteforge.automation.gelato_sync as gs
    monkeypatch.setattr(gs, "_uid_map", lambda: {})
    monkeypatch.setattr(ei, "store_products",
                        lambda: [{"id": "p2", "title": "no join key"}])
    r = ts.sync_template_images()
    assert r["checked"] == 1 and r["upserted"] == 0
    assert db.get_product_images() == []


def test_sync_never_raises_on_store_error(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    _go_live(monkeypatch)

    def _boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(ei, "store_products", _boom)
    # retry_call re-raises non-transient after attempts; sync must catch -> failed[]
    import quoteforge.automation.retry as rt
    monkeypatch.setattr(rt, "retry_call", lambda f, **k: f())   # no sleeps
    r = ts.sync_template_images()
    assert r["enabled"] is True and r["failed"] and r["failed"][0]["sku"] == "*"


# ── Etsy image getter (#181) ────────────────────────────────────

def test_etsy_get_listing_images_noop_without_creds():
    from quoteforge.automation import etsy_api
    assert etsy_api.get_listing_images("123") == []          # TEST_MODE / no creds
    assert etsy_api.official_listing_images("123") == {}


def test_official_listing_images_picks_rank_1_and_2(monkeypatch):
    from quoteforge.automation import etsy_api
    monkeypatch.setattr(etsy_api, "get_listing_images", lambda lid: [
        {"listing_image_id": 3, "rank": 2, "url_fullxfull": "https://e/life.jpg"},
        {"listing_image_id": 1, "rank": 1, "url_fullxfull": "https://e/studio.jpg"},
        {"listing_image_id": 9, "rank": 5, "url_fullxfull": "https://e/other.jpg"},
    ])
    out = etsy_api.official_listing_images("123")
    assert out == {"studio": "https://e/studio.jpg", "lifestyle": "https://e/life.jpg"}
