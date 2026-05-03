"""
Configuration settings loaded from environment variables.

Product-specific vars use THERAPY_ prefix to avoid collisions.
Global vars (SUPABASE_*, JWT_SECRET, OPENAI_API_KEY, etc.) are shared
across all products via the root .env file.
"""
from typing import Optional

from noctusai_seed import ProductSettings


class TherapySettings(ProductSettings):
    """Therapy Platform specific application settings."""

    # CORS — Therapy frontend default port
    cors_origins: str = "http://localhost:8095,http://localhost:5173,http://localhost:3000"

    # AI (global — shared with other products)
    openai_api_key: Optional[str] = None

    # Email (global — shared with other products)
    resend_api_key: Optional[str] = None
    email_from: str = "noreply@noctus.app"
    email_from_name: str = "NoctusAI Therapy"

    # Payments (global Stripe key + product-specific Connect client ID)
    stripe_secret_key: Optional[str] = None
    therapy_stripe_connect_client_id: Optional[str] = None

    # LiveKit (product-specific)
    therapy_livekit_url: Optional[str] = None
    therapy_livekit_api_key: Optional[str] = None
    therapy_livekit_api_secret: Optional[str] = None

    # Google OAuth + Calendar (product-specific)
    therapy_google_client_id: Optional[str] = None
    therapy_google_client_secret: Optional[str] = None

    # Scheduler — daily audio-retention sweep + future therapy retention jobs.
    # Default ON in prod; the FastAPI TestClient skips lifespan unless used as
    # a context manager so tests are safe. Set to False in any env that should
    # not sweep (local dev pointed at live DB, etc.).
    therapy_scheduler_enabled: bool = True
    therapy_audio_retention_sweep_interval_hours: int = 24


settings = TherapySettings()
