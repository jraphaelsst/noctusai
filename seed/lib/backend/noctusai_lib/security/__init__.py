"""Security primitives shared across NoctusAI products.

Currently exposes webhook signature verification (`webhook_signatures`),
at-rest secret encryption (`encrypted_tokens`), the per-(org, provider)
encrypted credential store (`token_store` — Protocol + Fake + Real +
factory), the app-wide encrypted key→value config store (`app_config` —
Protocol + Fake + Real + factory, sibling of `token_store` keyed on a
single ``key`` instead of ``(org_id, provider)``), the generic OAuth
callback infrastructure (`oauth` — Protocol + Google + Fake + factory +
`oauth_router`), and the content secret scan (`secrets_scan` —
`find_secret`/`has_secret`, hoisted A1c from the academia importer + the
`knowledge_bundle_export` MCP tool). Future additions (request rate
limiters) live here too.
"""

from noctusai_lib.security.api_keys import (
    ApiKeyOption,
    ApiKeyResolution,
    ApiKeySource,
    ApiKeySpec,
    EncryptionNotConfigured,
    PROVIDER_PREFIX,
    build_api_key_store,
    credentials_table_ddl,
    delete_api_key,
    make_local_credential_override,
    mask_value,
    provider_for,
    put_api_key,
    read_local_api_key,
    require_fernet,
    resolve_api_key,
    resolve_api_key_detail,
)
from noctusai_lib.security.app_config import (
    AppConfigDecryptError,
    AppConfigStore,
    CachedAppConfigStore,
    FakeAppConfigStore,
    RealAppConfigStore,
    build_app_config_store,
    resolve_app_config_value,
    resolve_meta_app_credentials,
)
from noctusai_lib.security.encrypted_tokens import (
    MultiKeyDecryptor,
    decrypt,
    encrypt,
    generate_key,
    rotate_key,
)
from noctusai_lib.security.webhook_signatures import (
    DEFAULT_MAX_AGE_SECONDS,
    GRUPO_OLX_BASIC_USERNAME,
    ResolvedSecret,
    SecretResolver,
    VerifiedWebhook,
    WebhookScheme,
    compute_hmac_sha256_hex,
    static_secret_resolver,
    verify_basic_shared_secret,
    verify_hmac_sha256,
    verify_hmac_sha256_hex,
    verify_svix_signature,
    webhook_endpoint,
)
from noctusai_lib.security import oauth
from noctusai_lib.security.secrets_scan import find_secret, has_secret
from noctusai_lib.security.token_store import (
    CredentialDecryptError,
    CredentialStore,
    FakeCredentialStore,
    StoredCredential,
    SupabaseCredentialStore,
    make_credential_store,
)

__all__ = [
    "ApiKeyOption",
    "ApiKeyResolution",
    "ApiKeySource",
    "ApiKeySpec",
    "AppConfigDecryptError",
    "AppConfigStore",
    "CachedAppConfigStore",
    "CredentialDecryptError",
    "CredentialStore",
    "DEFAULT_MAX_AGE_SECONDS",
    "EncryptionNotConfigured",
    "FakeAppConfigStore",
    "FakeCredentialStore",
    "GRUPO_OLX_BASIC_USERNAME",
    "MultiKeyDecryptor",
    "PROVIDER_PREFIX",
    "RealAppConfigStore",
    "ResolvedSecret",
    "StoredCredential",
    "SupabaseCredentialStore",
    "build_api_key_store",
    "build_app_config_store",
    "credentials_table_ddl",
    "delete_api_key",
    "make_credential_store",
    "make_local_credential_override",
    "mask_value",
    "provider_for",
    "put_api_key",
    "read_local_api_key",
    "require_fernet",
    "resolve_api_key",
    "resolve_api_key_detail",
    "SecretResolver",
    "VerifiedWebhook",
    "WebhookScheme",
    "compute_hmac_sha256_hex",
    "decrypt",
    "encrypt",
    "find_secret",
    "generate_key",
    "has_secret",
    "oauth",
    "resolve_app_config_value",
    "resolve_meta_app_credentials",
    "rotate_key",
    "static_secret_resolver",
    "verify_basic_shared_secret",
    "verify_hmac_sha256",
    "verify_hmac_sha256_hex",
    "verify_svix_signature",
    "webhook_endpoint",
]
