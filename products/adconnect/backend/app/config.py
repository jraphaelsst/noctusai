"""
AdConnect configuration.

Extends the framework's ProductSettings — no domain-specific fields needed.
This is the minimal config for a product that's just the spine.
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """AdConnect specific settings. No extras — just the framework baseline."""

    cors_origins: str = "http://localhost:8007,http://localhost:8130,http://localhost:5173,http://localhost:3000"


settings = SeedSettings()
