"""dev-team product configuration.

Extends the framework's `ProductSettings` — same Supabase + LLM env shape
used by every other product. The dev-team product itself doesn't add many
fields; the LLM provider keys are read by the engine (`dev_team/`) on its
own from the same env.
"""
from noctusai_seed import ProductSettings


class DevTeamSettings(ProductSettings):
    """dev-team product settings."""

    cors_origins: str = (
        "http://localhost:8009,"
        "http://localhost:8123,"
        "http://localhost:5173,"
        "http://localhost:3000"
    )


settings = DevTeamSettings()
