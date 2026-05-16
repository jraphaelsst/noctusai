"""
Base configuration for all NoctusAI products.

Products extend ProductSettings with their domain-specific fields.
The structural fields (JWT, CORS, core URL) are standardized here.
"""
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import SettingsConfigDict
from noctusai_lib.config import BaseAppSettings

_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class ProductSettings(BaseAppSettings):
    """Base settings that every product inherits.

    Provides:
      - JWT secret with production safety validation
      - Core API URL for cross-product communication
      - CORS origins

    Products extend this with domain-specific fields::

        class MailingSettings(ProductSettings):
            resend_api_key: str = ""
            max_sends_per_hour: int = 1000
    """

    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret: str = "noctus-dev-secret-change-in-prod"
    core_api_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Inbound request body cap. Applies to every endpoint via
    # `MaxBodySizeMiddleware`; bumps the 1 MB default for products that
    # legitimately receive large payloads (file-upload-via-webhook, etc.).
    max_body_bytes: int = 1 * 1024 * 1024  # 1 MB

    # Rate limit applied to inbound webhook routes via the product's
    # slowapi `@limiter.limit(settings.webhook_rate_limit)` decorator.
    # Tuned generous-but-not-absurd: providers commonly burst on retry
    # (Meta / Resend redrive a queue on outage), but a single attacker
    # IP shouldn't sustain hundreds per minute. Override per product if
    # legitimate burst exceeds the default.
    webhook_rate_limit: str = "60/minute"

    # ── Dev-auth (pre-seeded local identity) ──────────────────────────
    # Explicit, double-gated bypass for "scaffolded product runs
    # end-to-end on day one" (see noctusai_seed.dev_auth). MUST be off in
    # production: a `seed_dev_auth=True` in a non-debug env still cannot
    # activate (the factory requires BOTH this flag AND `debug`). Set
    # `SEED_DEV_AUTH=true` on the local/template .env, never on prod
    # compose/CI. `local_dev_user_id` / `local_dev_org_id` let a product
    # pin the synthesized identity to its own seeded org row when it has
    # one; defaults are fixed sentinels otherwise.
    seed_dev_auth: bool = False
    local_dev_user_id: str = ""
    local_dev_org_id: str = ""

    @field_validator("seed_dev_auth")
    @classmethod
    def validate_seed_dev_auth(cls, v, info):
        """Fail loud if dev-auth is requested in a production-shaped env.

        Mirrors the ``jwt_secret`` guard: a non-debug deploy that still
        carries ``SEED_DEV_AUTH=true`` is a misconfiguration that would
        otherwise become a silent auth backdoor.
        """
        debug = info.data.get("debug", True) if info.data else True
        if v and not debug:
            raise ValueError(
                "SECURITY ERROR: SEED_DEV_AUTH is true but debug is off. "
                "The dev-auth bypass must NEVER be enabled in production. "
                "Unset SEED_DEV_AUTH (or set DEBUG=true only in local dev)."
            )
        return v

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v, info):
        """Fail if using default JWT secret in production."""
        debug = info.data.get("debug", True) if info.data else True
        if v == "noctus-dev-secret-change-in-prod" and not debug:
            raise ValueError(
                "SECURITY ERROR: JWT_SECRET must be changed from default value in production. "
                "Set JWT_SECRET environment variable to a secure random string."
            )
        return v
