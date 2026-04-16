"""
ERP Imobiliario configuration — extends seed framework.
"""
from typing import Optional

from noctusai_seed import ProductSettings


class ERPSettings(ProductSettings):
    """ERP-specific application settings."""

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


settings = ERPSettings()
