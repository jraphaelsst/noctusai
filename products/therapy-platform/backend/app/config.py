"""
Configuration settings loaded from environment variables.

Product-specific vars use THERAPY_ prefix to avoid collisions.
Global vars (SUPABASE_*, JWT_SECRET, OPENAI_API_KEY, etc.) are shared
across all products via the root .env file.
"""
from pathlib import Path
from typing import Optional
from pydantic import field_validator
from noctusai_shared.config import BaseAppSettings

_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseAppSettings):
    """Therapy Platform specific application settings."""

    # JWT / SSO
    jwt_secret: str = "noctus-dev-secret-change-in-prod"
    core_api_url: str = "http://localhost:8000"

    # CORS — Therapy frontend default port
    cors_origins: str = "http://localhost:8095,http://localhost:5173,http://localhost:3000"

    # AI (global — shared with other products)
    openai_api_key: Optional[str] = None

    # Email (global — shared with other products)
    resend_api_key: Optional[str] = None
    email_from: str = "noreply@noctus.app"
    email_from_name: str = "NoctusAI Therapy"

    # Payments (global Stripe key + product-specific Connect client ID)
    stripe_secret_key: Optional[str] = None
    therapy_stripe_connect_client_id: Optional[str] = None

    # LiveKit (product-specific)
    therapy_livekit_url: Optional[str] = None
    therapy_livekit_api_key: Optional[str] = None
    therapy_livekit_api_secret: Optional[str] = None

    # Google OAuth + Calendar (product-specific)
    therapy_google_client_id: Optional[str] = None
    therapy_google_client_secret: Optional[str] = None

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

    class Config:
        env_file = str(_ROOT_ENV)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
