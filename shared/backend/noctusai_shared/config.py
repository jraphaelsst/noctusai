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

    # App
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://localhost:3000"
    debug: bool = False

    # Observability (optional — graceful degradation if not set)
    sentry_dsn: Optional[str] = None
    redis_url: Optional[str] = None

    # Pagination defaults
    default_page_size: int = 50
    max_page_size: int = 200

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return not self.debug
