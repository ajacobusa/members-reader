"""Ecommerce official-image auto-pull (#180) — gated, safe, self-diagnosing.

The connected Gelato ecommerce store has 0 products today, so these use mocked HTTP
to prove the LOGIC: the gate no-ops safely, a store product's previewUrl maps back to
our SKU via a confident join, and everything fails safe on bad/empty data."""
import pytest

import quoteforge.automation.ecommerce_images as ei


@pytest.fixture(autouse=True)
def _reset_memo():
    """Zero the per-process image memo before/after each test so a live-mode test
    can never leak {sku: url} into a later one (audit L2)."""
    ei._IMG_CACHE = None
    yield
    ei._IMG_CACHE = None


class _Resp:
    def __init__(self, code, payload):
        self.status_code = code
        self._p = payload

    def json(self):
        return self._p


def _go_live(monkeypatch, store="store-1"):
    import quoteforge.config as cfg
    import quoteforge.automation.gelato_api as ga
    monkeypatch.setattr(cfg, "TEST_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "GELATO_STORE_ID", store, raising=False)
    monkeypatch.setattr(cfg, "GELATO_ECOMMERCE_URL",
                        "https://ecommerce.gelatoapis.com", raising=False)
    monkeypatch.setattr(ga, "GELATO_API_KEY", "test-key", raising=False)
    ei._IMG_CACHE = None


def _mock_http(monkeypatch, list_payload, detail_payload, seen_headers=None):
    import requests

    def fake_get(url, headers=None, timeout=None, **kw):
        if seen_headers is not None:
            seen_headers.append(headers or {})
        if url.endswith("/products"):
            return _Resp(200, list_payload)
        if "/products/" in url:
            return _Resp(200, detail_payload)
        return _Resp(404, {})
    monkeypatch.setattr(requests, "get", fake_get)


def test_safe_noop_in_test_mode():
    # Default TEST_MODE=True -> disabled, no network, empty map.
    ei._IMG_CACHE = None
    assert ei.images_by_sku(refresh=True) == {}
    st = ei.status()
    assert st["enabled"] is False and st["mapped"] == 0


def test_maps_via_external_id(monkeypatch):
    # A store product carrying our SKU as externalId -> {sku: previewUrl}.
    _go_live(monkeypatch)
    seen = []
    _mock_http(monkeypatch,
               {"products": [{"id": "p1", "externalId": "GEL-CLASSIC_MUG-11OZ-WHITE"}]},
               {"previewUrl": "https://s3.example/mug.jpg"}, seen_headers=seen)
    out = ei.images_by_sku(refresh=True)
    assert out == {"GEL-CLASSIC_MUG-11OZ-WHITE": "https://s3.example/mug.jpg"}
    # REGRESSION: the Cloudflare-required User-Agent must be sent on every call.
    assert all("User-Agent" in h for h in seen) and seen


def test_maps_via_variant_uid_reverse_lookup(monkeypatch):
    # No externalId -> join a variant's Gelato productUid back through the SKU->UID map.
    _go_live(monkeypatch)
    import quoteforge.automation.gelato_sync as gs
    monkeypatch.setattr(gs, "_uid_map", lambda: {"OUR-TUMBLER": "bottle_real_uid_123"})
    _mock_http(monkeypatch,
               {"products": [{"id": "p9", "variants": [{"productUid": "bottle_real_uid_123"}]}]},
               {"previewUrl": "https://s3.example/tumbler.jpg"})
    out = ei.images_by_sku(refresh=True)
    assert out == {"OUR-TUMBLER": "https://s3.example/tumbler.jpg"}


def test_unmappable_product_is_skipped_and_self_reported(monkeypatch):
    # A product that joins to no SKU is SKIPPED (never guessed) and its raw keys are
    # surfaced in status() so the real join shape can be finalised.
    _go_live(monkeypatch)
    import quoteforge.automation.gelato_sync as gs
    monkeypatch.setattr(gs, "_uid_map", lambda: {})
    _mock_http(monkeypatch,
               {"products": [{"id": "p2", "title": "Mug", "someOtherKey": 1}]},
               {"previewUrl": "https://s3.example/x.jpg"})
    assert ei.images_by_sku(refresh=True) == {}
    st = ei.status()
    assert st["enabled"] is True and st["products"] == 1 and st["mapped"] == 0
    assert "someOtherKey" in st["unmapped_sample_keys"]


def test_empty_store_is_empty_map(monkeypatch):
    _go_live(monkeypatch)
    _mock_http(monkeypatch, {"products": []}, {})
    assert ei.images_by_sku(refresh=True) == {}


def test_never_raises_on_garbage(monkeypatch):
    _go_live(monkeypatch)
    _mock_http(monkeypatch, {"products": [None, 5, {"id": "p"}]}, {"nope": 1})
    # bad rows skipped, no image field -> empty, no exception
    assert ei.images_by_sku(refresh=True) == {}


def test_gelato_blank_image_prefers_ecommerce(monkeypatch):
    # gelato_blank_image returns the ecommerce previewUrl when present (before the
    # old catalog path), so the storefront tile auto-upgrades to the real photo.
    _go_live(monkeypatch)
    monkeypatch.setattr(ei, "images_by_sku",
                        lambda **k: {"SKU-1": "https://s3.example/real.jpg"})
    from quoteforge.images import supplier_mockup as sm
    assert sm.gelato_blank_image("SKU-1") == "https://s3.example/real.jpg"
