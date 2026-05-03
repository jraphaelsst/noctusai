"""Security primitives shared across NoctusAI products.

Currently exposes webhook signature verification (`webhook_signatures`).
Future additions (request rate limiters, secret-redaction helpers) live
here too.
"""

from noctusai_lib.security.webhook_signatures import (
    DEFAULT_MAX_AGE_SECONDS,
    ResolvedSecret,
    SecretResolver,
    VerifiedWebhook,
    WebhookScheme,
    compute_hmac_sha256_hex,
    static_secret_resolver,
    verify_hmac_sha256,
    verify_hmac_sha256_hex,
    verify_svix_signature,
    webhook_endpoint,
)

__all__ = [
    "DEFAULT_MAX_AGE_SECONDS",
    "ResolvedSecret",
    "SecretResolver",
    "VerifiedWebhook",
    "WebhookScheme",
    "compute_hmac_sha256_hex",
    "static_secret_resolver",
    "verify_hmac_sha256",
    "verify_hmac_sha256_hex",
    "verify_svix_signature",
    "webhook_endpoint",
]
