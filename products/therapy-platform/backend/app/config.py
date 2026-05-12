"""
Configuration settings loaded from environment variables.

Product-specific vars use THERAPY_ prefix to avoid collisions.
Global vars (SUPABASE_*, JWT_SECRET, OPENAI_API_KEY, etc.) are shared
across all products via the root .env file.
"""
from typing import Optional

from pydantic import AliasChoices, Field

from noctusai_seed import ProductSettings


class TherapySettings(ProductSettings):
    """Therapy Platform specific application settings."""

    # CORS — Therapy frontend default port
    cors_origins: str = "@registry:own:therapy-platform"

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

    # Google OAuth + Calendar.
    # Dev convention (2026-05-11): platform-wide creds live at root `.env` as
    # `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` — one personal
    # account reused across all products. Per-product `THERAPY_GOOGLE_CLIENT_ID`
    # env var overrides the global value for production scoping (future).
    # AliasChoices makes pydantic try product-prefix first, then fall back to
    # the global key.
    therapy_google_client_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("THERAPY_GOOGLE_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_ID"),
    )
    therapy_google_client_secret: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("THERAPY_GOOGLE_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET"),
    )

    # Scheduler — daily audio-retention sweep + future therapy retention jobs.
    # Default ON in prod; the FastAPI TestClient skips lifespan unless used as
    # a context manager so tests are safe. Set to False in any env that should
    # not sweep (local dev pointed at live DB, etc.).
    therapy_scheduler_enabled: bool = True
    therapy_audio_retention_sweep_interval_hours: int = 24

    # Optional Postgres URL for SQLAlchemy-bound flows. Used today only by
    # `app.services.audit_hook` to INSERT into `therapy.tool_call_audits` via
    # the seed `make_audit_writer(db, ToolCallAudit)` factory. Empty → the
    # audit-hook lazy session factory returns None and the writer becomes a
    # noop with a debug log (best-effort guarantee — never breaks LLM
    # dispatch). Routers + admin CRUD use the Supabase admin client; the
    # SQLAlchemy session is a SECONDARY surface.
    postgres_url: str = ""


settings = TherapySettings()
