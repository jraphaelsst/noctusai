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
