"""
Configuration settings loaded from environment variables.
"""
from pathlib import Path
from pydantic import field_validator
from noctusai_shared.config import BaseAppSettings

_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseAppSettings):
    """Personal Finance specific application settings."""

    # JWT / SSO
    jwt_secret: str = "noctus-dev-secret-change-in-prod"
    core_api_url: str = "http://localhost:8000"

    # CORS — PF frontend default port
    cors_origins: str = "http://localhost:8090,http://localhost:5173,http://localhost:3000"

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
