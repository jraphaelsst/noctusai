"""
Configuration settings loaded from environment variables.
"""
from pathlib import Path
from typing import Optional
from noctusai_shared.config import BaseAppSettings

_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseAppSettings):
    """ERP-specific application settings."""

    # JWT / SSO
    core_api_url: str = "http://localhost:8000"

    # CORS — ERP frontend default port
    cors_origins: str = "http://localhost:8080,http://localhost:5173,http://localhost:3000"

    # AI (optional — graceful degradation if not set)
    openai_api_key: Optional[str] = None

    # Email (optional — dry-run if not set)
    resend_api_key: Optional[str] = None
    email_from: str = "noreply@noctus.app"
    email_from_name: str = "NoctusAI ERP"

    # InfoSimples (optional — dry-run if not set)
    infosimples_token: Optional[str] = None

    # Digital signatures (optional — internal mock if not set)
    clicksign_api_token: Optional[str] = None
    clicksign_environment: str = "sandbox"
    docusign_integration_key: Optional[str] = None
    docusign_account_id: Optional[str] = None
    d4sign_api_token: Optional[str] = None
    d4sign_crypt_key: Optional[str] = None

    class Config:
        env_file = str(_ROOT_ENV)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
