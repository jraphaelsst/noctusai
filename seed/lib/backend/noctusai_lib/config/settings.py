"""
Base application settings shared by all NoctusAI backends.

Each product extends BaseAppSettings with product-specific fields
(e.g., openai_api_key for ERP, stripe keys for Core). The base
contains only the fields that every backend needs.
"""
from __future__ import annotations

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class BaseAppSettings(BaseSettings):
    """
    Shared settings base for all NoctusAI backends.

    Product backends create their own Settings(BaseAppSettings) and
    add product-specific fields. The env_file path and Config class
    must be set by the product since each backend resolves the root
    .env from a different __file__ location.
    """

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # JWT / SSO
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # Optional dedicated signing secret for SSO bridge tokens (core-only).
    # When set, SSO tokens are signed with this secret instead of jwt_secret,
    # decoupling bridge-token signing from per-product session signing.
    # A leaked product jwt_secret cannot forge SSO identities when this is set.
    # Empty default → falls back to jwt_secret (zero-config back-compat).
    sso_jwt_secret: str = ""

    # App
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://localhost:3000"
    debug: bool = False

    # Observability (optional — graceful degradation if not set)
    sentry_dsn: Optional[str] = None
    redis_url: Optional[str] = None

    # App-held Fernet key (44 url-safe-base64 chars, from `generate_key()`)
    # used to encrypt auth-session tokens AT REST in the shared fleet Redis
    # (SEC-3 of the httpOnly-cookie-session roadmap). The Supabase refresh
    # token is a long-lived full-impersonation credential; storing it
    # plaintext in a Redis shared with the LLM cache + rate-limiter means a
    # single Redis read harvests every user's credential. When set, the
    # RedisSessionStore encrypts `refresh_token` + cached `access_token`
    # before write and decrypts on read; when empty, tokens are stored
    # plaintext (acceptable ONLY for the in-memory FakeSessionStore / local
    # dev with no real refresh tokens — the factory refuses a Redis store
    # without a key when `require_encryption` is set). Store OUT-OF-BAND
    # from Redis (env var `REDIS_SESSION_ENCRYPTION_KEY` / secret manager);
    # rotate via `MultiKeyDecryptor`. Named `redis_*` (not just
    # `session_*`) to disambiguate from the sibling app-config/credential
    # at-rest `ENCRYPTION_KEY` in `security/app_config.py` — the two are
    # unrelated and are routinely confused.
    redis_session_encryption_key: str = ""

    # LLM usage tracking (Phase 15) — opt-in per product via env var.
    # When true, create_product_app() constructs a SupabaseUsageSink that
    # writes every `UsageEvent` to `<schema>.llm_usage`.
    llm_usage_tracking: bool = False

    # Pagination defaults
    default_page_size: int = 50
    max_page_size: int = 200

    @property
    def cors_origins_list(self) -> list[str]:
        """Resolve `cors_origins` into a concrete list of origin strings.

        Recognized forms (checked in order):

        - ``"*"``                          → ``["*"]`` (legacy; only valid
          when ``allow_credentials`` is OFF — see MDN auth-replay
          anti-pattern).
        - ``"@registry:all"``              → every product frontend from
          ``start.sh PRODUCTS`` + localhost alts. SSO-bridge shape.
        - ``"@registry:own:<slug>"``       → that product's frontend +
          localhost alts. Single-product shape.
        - plain comma-separated string     → ``[s.strip() for s in split(",")]``.

        See :mod:`noctusai_lib.config.cors_registry`.
        """
        raw = self.cors_origins
        if raw == "*":
            return ["*"]
        if raw.startswith("@registry:"):
            # Lazy import — keeps the public surface of `noctusai_lib.config`
            # narrow and avoids a circular hop during settings bootstrap.
            from noctusai_lib.config.cors_registry import derive_cors_origins

            spec = raw.split(":", 2)  # ["@registry", "<mode>", "<slug?>"]
            mode = spec[1] if len(spec) >= 2 else ""
            if mode == "all":
                return derive_cors_origins(include_all_frontends=True)
            if mode == "own" and len(spec) == 3 and spec[2]:
                return derive_cors_origins(
                    include_all_frontends=False,
                    own_slug=spec[2],
                )
            # Unknown sentinel — fall back to localhost alts only (no crash).
            return derive_cors_origins(
                include_all_frontends=False,
                own_slug=None,
            )
        return [origin.strip() for origin in raw.split(",")]

    @property
    def is_production(self) -> bool:
        return not self.debug
