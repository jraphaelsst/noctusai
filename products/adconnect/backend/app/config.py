"""
AdConnect configuration.

Extends the framework's ProductSettings — no domain-specific fields needed.
This is the minimal config for a product that's just the spine.
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """AdConnect specific settings. No extras — just the framework baseline."""

    cors_origins: str = "http://localhost:8007,http://localhost:8130,http://localhost:5173,http://localhost:3000"

    # Test-only JWT secret. Production auth goes through the seed's
    # `make_get_current_user` factory (Supabase-backed), NOT a custom
    # JWT verifier. This field exists ONLY so tests can mint signed
    # tokens for header-shape compatibility — `MockSupabaseClient.auth.
    # get_user` is patched to ignore the token content and return a
    # configured MockUser. Do NOT reintroduce `app/security.py` or any
    # custom JWT verification path keyed off this secret.
    jwt_secret: str = "test-only-jwt-secret-do-not-use-in-prod"


settings = SeedSettings()
