"""
{{PRODUCT_NAME}} configuration.

Extends the framework's ProductSettings — no domain-specific fields needed.
This is the minimal config for a product that's just the spine.
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """{{PRODUCT_NAME}} specific settings. No extras — just the framework baseline."""

    cors_origins: str = "http://localhost:{{BACKEND_PORT}},http://localhost:{{FRONTEND_PORT}},http://localhost:5173,http://localhost:3000"


settings = SeedSettings()
