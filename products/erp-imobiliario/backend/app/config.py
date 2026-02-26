"""
Configuration settings loaded from environment variables.
"""
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings

_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    """Application settings from .env file."""

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # App
    cors_origins: str = "http://localhost:8080,http://localhost:5173,http://localhost:3000"
    debug: bool = True

    # JWT / SSO (must match Core platform's jwt_secret)
    jwt_secret: str = "noctus-dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    core_api_url: str = "http://localhost:8001"

    # Observability (optional - graceful degradation if not set)
    sentry_dsn: Optional[str] = None
    redis_url: Optional[str] = None

    # AI (optional - graceful degradation if not set)
    openai_api_key: Optional[str] = None

    # Pagination defaults
    default_page_size: int = 50
    max_page_size: int = 200

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return not self.debug

    class Config:
        env_file = str(_ROOT_ENV)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
