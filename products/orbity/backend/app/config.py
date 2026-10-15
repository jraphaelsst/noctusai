"""
Orbity configuration.

Extends the framework's ProductSettings — minimal additions (currently none beyond the CORS registry entry).
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Orbity specific settings."""

    cors_origins: str = "@registry:own:orbity"


settings = SeedSettings()
