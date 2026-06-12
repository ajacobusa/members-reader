"""Webhook signature verification.

Etsy/Make.com can sign webhook payloads with an HMAC-SHA256 signature.
Verifying it ensures the request genuinely came from your automation and
not an attacker spamming your /order endpoint.
"""
import hashlib
import hmac

from quoteforge.config import ETSY_WEBHOOK_SECRET, GELATO_WEBHOOK_SECRET


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 hex signature for a raw payload."""
    return hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()


def verify_signature(payload_bytes: bytes, provided_signature: str,
                     secret: str = "") -> bool:
    """Verify a webhook payload against its provided signature.

    If no secret is configured, verification is SKIPPED (returns True) so the
    system works in development. Set ETSY_WEBHOOK_SECRET in .env for production.
    """
    secret = secret or ETSY_WEBHOOK_SECRET
    return _verify(payload_bytes, provided_signature, secret)


def verify_gelato_signature(payload_bytes: bytes, provided_signature: str,
                            secret: str = "") -> bool:
    """Verify a Gelato status/tracking callback against its HMAC-SHA256 signature.

    Like verify_signature, but keyed on GELATO_WEBHOOK_SECRET. If no secret is
    configured, verification is skipped (returns True) for dev parity.
    """
    secret = secret or GELATO_WEBHOOK_SECRET
    return _verify(payload_bytes, provided_signature, secret)


def _verify(payload_bytes: bytes, provided_signature: str, secret: str) -> bool:
    """Constant-time HMAC check; skipped (True) when no secret is configured."""
    if not secret:
        return True  # no secret configured — verification disabled (dev mode)
    if not provided_signature:
        return False
    expected = compute_signature(payload_bytes, secret)
    # constant-time comparison to avoid timing attacks
    return hmac.compare_digest(expected, provided_signature.strip())
