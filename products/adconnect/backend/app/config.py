"""
AdConnect configuration.

Extends the framework's ProductSettings — no domain-specific fields needed.
This is the minimal config for a product that's just the spine.
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """AdConnect specific settings. No extras — just the framework baseline."""

    cors_origins: str = "@registry:own:adconnect"


settings = SeedSettings()
