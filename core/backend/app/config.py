"""
NoctusAI Core — Configuration settings.
"""
from typing import Optional
from pydantic_settings import BaseSettings


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

    @property
    def cors_origins_list(self) -> list:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
