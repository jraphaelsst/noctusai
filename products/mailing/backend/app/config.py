"""
Mailing Product configuration.

Extends the framework's ProductSettings with email-specific fields.
"""
from typing import Optional
from noctusai_seed import ProductSettings


class MailingSettings(ProductSettings):
    """Mailing-specific settings."""

    cors_origins: str = "@registry:own:mailing"

    # Resend
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    default_from_email: str = "noreply@noctusai.com"
    default_from_name: str = "NoctusAI Mailing"

    # Sending limits
    max_batch_size: int = 100
    max_sends_per_hour: int = 1000

    # Scheduler intervals
    send_loop_seconds: int = 30
    automation_check_minutes: int = 5
    scheduled_campaign_check_seconds: int = 60

    # Optional Postgres URL for SQLAlchemy-bound flows (LLM tool-call audit
    # writer — see `app/services/audit_hook.py`). Empty → audit-hook lazy
    # session factory returns None and the audit writer skips with a debug
    # log. Routers/services use the Supabase admin client per the seed
    # contract; SQLAlchemy is a SECONDARY surface for the audit-writer
    # only (llm-tool-audit-rollout Phase 3, 2026-05-11).
    postgres_url: str = ""


settings = MailingSettings()
