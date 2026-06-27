"""Shared test configuration.

The PRODUCTION default for GELATO_FULFILLMENT_MODE is "native" (Gelato fulfils via its
native Etsy integration; QuoteForge does NOT submit to Gelato). The existing suite,
however, exercises the QuoteForge->Gelato submission path (route_order, the 7-stage
pipeline, vendor_order_id, delivery), so run those tests in "quoteforge" mode. The
native gate is covered explicitly by test_fulfillment_mode.py.
"""
import pytest


@pytest.fixture(autouse=True)
def _fulfillment_mode_quoteforge(monkeypatch):
    import quoteforge.config as cfg
    monkeypatch.setattr(cfg, "GELATO_FULFILLMENT_MODE", "quoteforge", raising=False)
