"""
Imobi Scheduling configuration.

Extends ``ProductSettings`` (which extends ``noctusai_lib.config.BaseAppSettings``)
— the canonical seed-product pattern. ``BaseAppSettings`` provides Supabase /
JWT / CORS / observability fields used by every product (`KB §
PATTERNS/environment.md`); ``ProductSettings`` layers in JWT-default safety,
``core_api_url``, ``max_body_bytes``, and ``webhook_rate_limit``. This class
adds product-specific overrides + **forward-compat STUBS** for the
integration env-vars consumed by Phases 5 (WAHA), 8 (Google Calendar /
Maps), and beyond. Empty defaults keep the schema valid in dev without
forcing the operator to populate them before they're wired.
"""
from typing import Optional

from noctusai_seed import ProductSettings


class ImobiSchedulingSettings(ProductSettings):
    """Imobi Scheduling specific settings."""

    cors_origins: str = "http://localhost:8011,http://localhost:8160,http://localhost:5173,http://localhost:3000"

    # ── Webhook receiver (consumed by app/routers/webhook_router.py) ──
    # Empty by default → ``webhook_endpoint(bypass_when_unset=True)``
    # accepts unsigned payloads with a WARNING (early-dev only). Set in
    # ``.env`` (``EXAMPLE_WEBHOOK_SECRET=…``) to enforce verification.
    # Rename per vendor (``resend_webhook_secret`` / ``meta_webhook_secret`` / etc.).
    example_webhook_secret: str = ""

    # Rate-limit for webhook endpoints (per-IP). Public surface — DDOS guard.
    webhook_rate_limit: str = "60/minute"

    # ── Phase 3 — Supabase wiring (forward-compat stubs) ──
    # BaseAppSettings already provides `supabase_url` / `supabase_anon_key` /
    # `supabase_service_role_key` (cross-product convention). Per-product
    # schema-scoped helpers consume those directly; no per-product field
    # needed here.

    # ── Phase 5 — WhatsApp / WAHA wiring (LIVE) ──
    # The connector lives at `noctusai_lib.integrations.whatsapp`. The
    # product mounts the seed factory ``create_whatsapp_webhook_router``
    # via ``app/routers/whatsapp_router.py``. Defaults stay empty so the
    # schema is valid in early-dev — empty ``waha_base_url`` means the
    # factory ``get_whatsapp_client()`` returns the in-memory FakeWahaClient
    # per `KB § PATTERNS/seed-fake-real-adapter.md`. Empty
    # ``imobi_whatsapp_webhook_secret`` engages signature-bypass mode at
    # the seed router (logs WARNING; pin 3 of the 5-pin contract).
    waha_base_url: Optional[str] = None
    waha_api_key: Optional[str] = None
    waha_session_name: str = "imobi_scheduling"
    """WAHA session name (env: WAHA_SESSION_NAME). Defaults to the
    product slug — single-session per deployment in v1."""
    imobi_whatsapp_webhook_secret: Optional[str] = None
    """HMAC-SHA256 hex secret WAHA signs inbound webhooks with
    (env: IMOBI_WHATSAPP_WEBHOOK_SECRET). When None, the seed router
    skips signature verification + logs a WARNING. Set in ``.env``
    to enforce pins 1-3 of the webhook 5-pin compliance contract."""
    conversation_memory_ttl_seconds: int = 3600
    message_debounce_seconds: int = 8

    # ── Phase 8 — Google Calendar wiring (forward-compat stubs) ──
    # Adapter shape: OAuth client + service-account JSON path + Fake.
    # Picked up by `configure_calendar_module(...)`. See `KB §
    # PATTERNS/whatsapp-chatbot-seed.md` for the wiring recipe.
    google_calendar_oauth_client_id: Optional[str] = None
    google_calendar_oauth_client_secret: Optional[str] = None
    google_calendar_service_account_file: Optional[str] = None
    google_calendar_default_calendar_id: Optional[str] = None

    # ── Phase 8 — Google Maps wiring (forward-compat stubs) ──
    # Routes / Distance Matrix + static-routing fallback live at
    # `noctusai_lib.integrations.google_maps`; configured via
    # `configure_maps_module(...)`.
    google_maps_api_key: Optional[str] = None

    # ── Phase 6 — OpenAI / LLM tool-loop (forward-compat) ──
    # The default LLM config is wired automatically by
    # `create_product_app(...)`; this override exists so the bot can pin
    # a model independent of the platform-wide default.
    openai_model: str = "gpt-4o-mini"

    # ── Phase 7 — Scheduling engine knobs (LIVE) ──
    # Consumed by `app/services/scheduling.py` when it builds
    # `noctusai_lib.domain.scheduling.SchedulingRules`. Defaults match
    # Engineer-E's Phase 0 sibling audit:
    #   morning  09:00-12:00
    #   lunch    12:00-13:30  (implicit gap between morning_end and afternoon_start)
    #   afternoon 13:30-16:30
    #   travel buffer    10 min
    #   standard slot    90 min
    #   same-condo slot  60 min  (back-to-back at same location shortens)
    #   slot grid        30 min  (cursor stride during candidate generation)
    imobi_scheduling_timezone: str = "America/Sao_Paulo"
    imobi_scheduling_morning_start: str = "09:00"
    imobi_scheduling_morning_end: str = "12:00"
    imobi_scheduling_afternoon_start: str = "13:30"
    imobi_scheduling_afternoon_end: str = "16:30"
    imobi_scheduling_travel_buffer_minutes: int = 10
    imobi_scheduling_standard_duration_minutes: int = 90
    imobi_scheduling_same_condo_duration_minutes: int = 60
    imobi_scheduling_slot_grid_minutes: int = 30


settings = ImobiSchedulingSettings()
