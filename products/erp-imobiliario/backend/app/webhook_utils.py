"""
Shared webhook verification utilities.

Thin re-export layer over `noctusai_lib.security.webhook_signatures` so
existing call sites (`from app.webhook_utils import verify_hmac_sha256`)
keep working while the canonical implementation lives in the platform
shared library. New code should import from `noctusai_lib.security`
directly.
"""

from noctusai_lib.security.webhook_signatures import (  # noqa: F401
    compute_hmac_sha256_hex,
    verify_hmac_sha256,
    verify_svix_signature,
)
