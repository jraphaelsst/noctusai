"""
Media Scheduling configuration.

Extends the framework's ProductSettings with the WAHA / Redis / OpenAI /
Google-OAuth fields the WhatsApp-driven scheduling flow needs (Phase 3+).
All defaults are empty strings so the app boots in unconfigured-dev mode
(webhook signature verification falls back to the bypass-with-WARNING
path; the worker is registered but no-ops without Redis).
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """Media Scheduling settings.

    Phase 3 fields: Redis URL (chatbot buffer), WAHA inbound HMAC secret +
    base URL/api-key/session (outbound sender), OpenAI chat model
    selector, Google Calendar OAuth client/secret/redirect, optional
    Postgres URL for SQLAlchemy-bound flows (audit hook).
    """

    cors_origins: str = "@registry:own:media-scheduling"

    # Redis (chatbot buffer + debounce). Empty → worker logs a warning at startup
    # and skips the run-loop; webhook still verifies + parses inbound payloads.
    redis_url: str = ""

    # WAHA inbound webhook HMAC secret (sha256_hex via X-Webhook-Hmac-SHA256
    # header). Empty triggers the seed `bypass_when_unset=True` early-dev path
    # (logs WARNING; accepts unsigned payloads).
    waha_webhook_secret: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    # Webhook-compliance pin #4 — see KB § PATTERNS/webhook-signatures.md.
    webhook_rate_limit: str = "60/minute"

    # WAHA outbound sender. Empty → seed `get_whatsapp_client()` returns
    # `FakeWahaClient` (records sent_messages in-memory, useful for tests).
    waha_base_url: str = ""
    waha_api_key: str = ""
    waha_session: str = "default"
    waha_log_raw_webhooks: bool = False

    # OpenAI LLM dispatcher model selector.
    openai_chat_model: str = "gpt-4o-mini"

    # Google Calendar OAuth (single-account-per-product flow). Empty → /oauth/google/init
    # returns 503 with explanation; /api/oauth/google/status returns
    # `{connected: false}`.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""

    # Conversation buffer timing knobs (mirror source defaults). Tuned safe for
    # WhatsApp's natural reply cadence — 8s debounce catches multi-bubble bursts;
    # 30 min idle window triggers summary persistence on dropped conversations.
    conversation_memory_ttl_seconds: int = 3600
    message_debounce_seconds: int = 8
    conversation_idle_timeout_seconds: int = 1800
    redis_stream_maxlen: int = 10_000
    worker_poll_seconds: float = 2.0
    worker_due_batch_size: int = 25

    # Optional Postgres URL for SQLAlchemy-bound flows (audit-hook write side
    # effects, future ORM-backed retention sweeps). Empty → audit-hook lazy
    # session factory returns None and the audit writer skips with a debug log.
    # Routers/admin CRUD use the Supabase admin client per PROJECT.md §2 — the
    # SQLAlchemy session is a SECONDARY surface, not the primary data path.
    postgres_url: str = ""


settings = SeedSettings()
