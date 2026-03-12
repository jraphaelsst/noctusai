"""
NoctusAI Core — Configuration settings.
"""
from pathlib import Path
from typing import Optional
from pydantic import field_validator
from noctusai_shared.config import BaseAppSettings

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseAppSettings):
    """Core platform specific settings."""

    # JWT
    jwt_secret: str = "noctus-dev-secret-change-in-prod"
    jwt_expiration_minutes: int = 60 * 24  # 24h

    # SSO
    sso_token_expiration_minutes: int = 5  # short-lived

    # App
    cors_origins: str = "*"

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    app_base_url: str = "http://localhost:5173"

    # Email (optional — Resend)
    resend_api_key: Optional[str] = None

    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, v, info):
        """Fail if using default JWT secret in production."""
        debug = info.data.get('debug', True) if info.data else True
        if v == "noctus-dev-secret-change-in-prod" and not debug:
            raise ValueError(
                "SECURITY ERROR: JWT_SECRET must be changed from default value in production. "
                "Set JWT_SECRET environment variable to a secure random string."
            )
        return v

    class Config:
        env_file = str(_ROOT_ENV)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
