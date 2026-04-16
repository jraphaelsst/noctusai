"""
Mailing Product configuration.

Extends the framework's ProductSettings with email-specific fields.
"""
from typing import Optional
from noctusai_seed import ProductSettings


class MailingSettings(ProductSettings):
    """Mailing-specific settings."""

    cors_origins: str = "http://localhost:8006,http://localhost:8120,http://localhost:5173,http://localhost:3000"

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


settings = MailingSettings()
