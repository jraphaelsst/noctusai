"""Security primitives shared across NoctusAI products.

Currently exposes webhook signature verification (`webhook_signatures`),
at-rest secret encryption (`encrypted_tokens`), the per-(org, provider)
encrypted credential store (`token_store` — Protocol + Fake + Real +
factory), and the generic OAuth callback infrastructure (`oauth` —
Protocol + Google + Fake + factory + `oauth_router`). Future additions
(request rate limiters, secret-redaction helpers) live here too.
"""

from noctusai_lib.security.encrypted_tokens import (
    MultiKeyDecryptor,
    decrypt,
    encrypt,
    generate_key,
    rotate_key,
)
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
from noctusai_lib.security import oauth
from noctusai_lib.security.token_store import (
    CredentialDecryptError,
    CredentialStore,
    FakeCredentialStore,
    StoredCredential,
    SupabaseCredentialStore,
    make_credential_store,
)

__all__ = [
    "CredentialDecryptError",
    "CredentialStore",
    "DEFAULT_MAX_AGE_SECONDS",
    "FakeCredentialStore",
    "MultiKeyDecryptor",
    "ResolvedSecret",
    "StoredCredential",
    "SupabaseCredentialStore",
    "make_credential_store",
    "SecretResolver",
    "VerifiedWebhook",
    "WebhookScheme",
    "compute_hmac_sha256_hex",
    "decrypt",
    "encrypt",
    "generate_key",
    "oauth",
    "rotate_key",
    "static_secret_resolver",
    "verify_hmac_sha256",
    "verify_hmac_sha256_hex",
    "verify_svix_signature",
    "webhook_endpoint",
]
