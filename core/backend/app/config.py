"""
NoctusAI Core — Configuration settings.
"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # JWT
    jwt_secret: str = "noctus-dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60 * 24  # 24h

    # SSO
    sso_token_expiration_minutes: int = 5  # short-lived

    # App
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"
    debug: bool = True

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    app_base_url: str = "http://localhost:5173"

    # Observability (optional)
    sentry_dsn: Optional[str] = None
    redis_url: Optional[str] = None

    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, v, info):
        """Fail if using default JWT secret in production."""
        # Access debug from info.data if available
        debug = info.data.get('debug', True) if info.data else True
        if v == "noctus-dev-secret-change-in-prod" and not debug:
            raise ValueError(
                "SECURITY ERROR: JWT_SECRET must be changed from default value in production. "
                "Set JWT_SECRET environment variable to a secure random string."
            )
        return v

    @property
    def cors_origins_list(self) -> list:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return not self.debug

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
