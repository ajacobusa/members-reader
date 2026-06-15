"""Preflight live-readiness regression tests.

In TEST_MODE the live credentials are optional (soft CONFIG). Once TEST_MODE is
OFF (going live), every required credential must be set or preflight FAILs
loudly - a missing key must not slip through as a green all-clear, because orders
would silently fail to route."""
from unittest.mock import patch

from quoteforge import preflight


def _live_readiness_result():
    return next(r for r in preflight.check_software()
                if "live readiness" in r.name.lower())


def test_live_readiness_passes_in_test_mode():
    from quoteforge import config
    with patch.object(config, "TEST_MODE", True):
        assert _live_readiness_result().status == "PASS"


def test_live_readiness_fails_when_live_and_keys_missing():
    from quoteforge import config
    with patch.object(config, "TEST_MODE", False), \
         patch.object(config, "ANTHROPIC_API_KEY", ""), \
         patch.object(config, "GELATO_API_KEY", ""), \
         patch.object(config, "ETSY_API_KEY", ""), \
         patch.object(config, "ETSY_WEBHOOK_SECRET", ""):
        r = _live_readiness_result()
        assert r.status == "FAIL"
        assert "missing" in r.detail.lower()
    # And the overall software gate must reflect the failure.
    with patch.object(config, "TEST_MODE", False), \
         patch.object(config, "ANTHROPIC_API_KEY", ""), \
         patch.object(config, "GELATO_API_KEY", ""), \
         patch.object(config, "ETSY_API_KEY", ""), \
         patch.object(config, "ETSY_WEBHOOK_SECRET", ""):
        assert preflight.run_preflight()["software_passed"] is False


def test_live_readiness_passes_when_live_and_keys_present():
    from quoteforge import config
    with patch.object(config, "TEST_MODE", False), \
         patch.object(config, "ANTHROPIC_API_KEY", "x"), \
         patch.object(config, "GELATO_API_KEY", "x"), \
         patch.object(config, "ETSY_API_KEY", "x"), \
         patch.object(config, "ETSY_WEBHOOK_SECRET", "x"):
        assert _live_readiness_result().status == "PASS"
