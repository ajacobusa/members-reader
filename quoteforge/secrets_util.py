"""Secure secret generation for webhook signing."""
import secrets


def generate_webhook_secret(nbytes: int = 32) -> str:
    """Generate a cryptographically secure URL-safe secret.

    Use the same value in your .env (ETSY_WEBHOOK_SECRET) and in the
    Make.com/Zapier HTTP module header X-Webhook-Signature signing step.
    """
    return secrets.token_urlsafe(nbytes)
