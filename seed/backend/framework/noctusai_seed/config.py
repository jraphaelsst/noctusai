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
