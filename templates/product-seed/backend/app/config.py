"""
{{PRODUCT_NAME}} — Configuration via Pydantic Settings.
Reads from the single root .env file.
"""
from pathlib import Path
from noctusai_shared.config import BaseAppSettings

# Resolve the root .env (4 levels up from this file: app/ → backend/ → product/ → products/ → root)
_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _ROOT / ".env"


class Settings(BaseAppSettings):
    # Product-specific settings go here.
    # Example:
    # my_product_api_key: str | None = None

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
