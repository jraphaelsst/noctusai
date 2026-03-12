"""
Shared webhook verification utilities.

Provides HMAC-SHA256 signature verification for webhook endpoints
(Meta Lead Ads, WhatsApp WAHA, signing providers, etc.).
"""
import hashlib
import hmac


def verify_hmac_sha256(body: bytes, signature: str, secret: str) -> bool:
    """
    Verify an HMAC-SHA256 webhook signature.

    Args:
        body: Raw request body bytes.
        signature: The signature header value (e.g. "sha256=abc123...").
        secret: The shared secret used to compute the expected signature.

    Returns:
        True if the signature is valid, False otherwise.
    """
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
