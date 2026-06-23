"""WhatsApp connector — WAHA inbound parser + outbound sender + webhook router.

Lifted from `whatsapp-google-scheduling/app/services/waha/` 2026-05-03
via `projects/whatsapp-seed-absorption/`. Provider-neutral by design —
swapping to Twilio / Cloud API later does not rename the public surface.

Reconciled 2026-05-16 to the live-validated `noctusai-youtube-crawler`
workspace (commits `598f8f7` LID-auth, `f9839d4`+`fedd4cf` dedup +
media-URL rewrite) via `projects/social-wiring-absorption/` Wave 1.E2.

Public surface:
- Types: `WhatsAppInboundMessage`, `WhatsAppMedia`, `WhatsAppPayloadError`,
  `WhatsAppIgnoredEvent`, `WhatsAppClient` Protocol. Legacy `Waha*`
  aliases preserved.
- Parsing: `parse_waha_inbound_message`, `chat_id_for_phone`,
  `phone_from_chat_id`, `build_send_text_body`,
  `rewrite_vendor_media_url`.
- HTTP: `WahaClient` (sync + async send_text + download_media;
  async list_chats + fetch_chat_messages — require NOWEB store enabled;
  start/restart_session include noweb store config by default;
  external→internal media-URL rewrite).
- Fake: `FakeWahaClient` — bi-directional in-memory deterministic
  (records `sent_messages`, accepts `inject_text` / `inject_inbound`,
  serves pre-populated `media_bytes`).
- Factory: `get_whatsapp_client(base_url=, api_key=, session=,
  external_base_url=)` — returns `WahaClient` when `base_url` is set,
  `FakeWahaClient` otherwise. Mirrors
  `google_calendar.get_calendar_adapter()` per
  `KB § PATTERNS/seed-fake-real-adapter.md`.
- @lid auth: `is_authorized` (3-tier), `resolve_canonical_session`,
  `remember_lid_phone`, `get_lid_phone_cache` (Protocol+Fake+Real).
- Webhook dedup: `WebhookDedup` Protocol + `RedisWebhookDedup`
  (SETNX pre-filter) + `InMemoryWebhookDedup` + `get_webhook_dedup`.
  DB UNIQUE backstop is the chatbot `message_store` seam (consumer
  composes both).
- WAHA response-shape registry: `ResponseRegistry` Protocol +
  `FakeResponseRegistry` + `PersistentResponseRegistry` +
  `get_response_registry` (drift observability side-car).
- FastAPI: `create_whatsapp_webhook_router(... , dedup=)` factory.
- Settings: `WhatsAppSettings` Pydantic model.

See `KB § PATTERNS/whatsapp-chatbot-seed.md` for the wiring recipe.
"""

from noctusai_lib.integrations.whatsapp.client import (
    WahaClient,
    WahaSessionNotReady,
)
from noctusai_lib.integrations.whatsapp.dedup import (
    InMemoryWebhookDedup,
    RedisWebhookDedup,
    SetnxRedis,
    WebhookDedup,
    get_webhook_dedup,
)
from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from noctusai_lib.integrations.whatsapp.lid_auth import (
    InMemoryLidPhoneCache,
    LidPhoneCache,
    RedisLidPhoneCache,
    extract_resolved_remote,
    get_lid_phone_cache,
    is_authorized,
    is_lid,
    is_phone_jid,
    normalize_phone,
    remember_lid_phone,
    resolve_canonical_session,
)
from noctusai_lib.integrations.whatsapp.meta_cloud_client import (
    DEFAULT_BASE_URL as META_CLOUD_DEFAULT_BASE_URL,
)
from noctusai_lib.integrations.whatsapp.meta_cloud_client import (
    FakeMetaCloudClient,
    MetaCloudClient,
)
from noctusai_lib.integrations.whatsapp.mappers import (
    build_send_text_body,
    chat_id_for_phone,
    parse_waha_inbound_message,
    phone_from_chat_id,
    rewrite_vendor_media_url,
)
from noctusai_lib.integrations.whatsapp.response_registry import (
    FakeResponseRegistry,
    PersistentResponseRegistry,
    ResponseRegistry,
    ResponseSample,
    ResponseSampleSink,
    fingerprint_response,
    get_response_registry,
)
from noctusai_lib.integrations.whatsapp.router import (
    InboundHandler,
    create_whatsapp_webhook_router,
)
from noctusai_lib.integrations.whatsapp.settings import WhatsAppSettings
from noctusai_lib.integrations.whatsapp.types import (
    WahaIgnoredEvent,
    WahaInboundMessage,
    WahaMedia,
    WahaPayloadError,
    WhatsAppClient,
    WhatsAppIgnoredEvent,
    WhatsAppInboundMessage,
    WhatsAppMedia,
    WhatsAppPayloadError,
)


def get_whatsapp_client(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    session: str = "default",
    external_base_url: str | None = None,
) -> WhatsAppClient:
    """Return a real WAHA client when `base_url` is set; `FakeWahaClient` otherwise.

    Mirrors `get_calendar_adapter()` and `get_routing_adapter()` shape per
    `KB § PATTERNS/seed-fake-real-adapter.md`. The presence of `base_url`
    is the configured-vs-not-configured signal — a real WAHA endpoint
    means we're talking to a real server.

    `external_base_url` is the browser-facing host WAHA *emits* in media
    URLs; `base_url` is the docker-internal host the app *reaches*.
    Defaults to `base_url` (single-host dev — rewrite no-op). See
    `WahaClient` docstring + SESSION-NOTES §4.3.
    """
    if not base_url:
        return FakeWahaClient(session=session)
    return WahaClient(
        base_url=base_url,
        api_key=api_key,
        session=session,
        external_base_url=external_base_url,
    )


def get_meta_cloud_client(
    *,
    phone_number_id: str | None = None,
    api_key: str | None = None,
    base_url: str = META_CLOUD_DEFAULT_BASE_URL,
) -> MetaCloudClient | FakeMetaCloudClient:
    """Return a real `MetaCloudClient` when `api_key` is set; `FakeMetaCloudClient` otherwise.

    Mirrors `get_whatsapp_client()` and `get_calendar_adapter()` factories per
    `KB § PATTERNS/seed-fake-real-adapter.md`. The presence of `api_key` is
    the configured-vs-not-configured signal — Meta Cloud API rejects all
    requests without a Bearer token, so an unset key means we are talking
    to a fake.
    """
    if not api_key:
        return FakeMetaCloudClient(
            phone_number_id=phone_number_id, base_url=base_url
        )
    return MetaCloudClient(
        phone_number_id=phone_number_id or "",
        api_key=api_key,
        base_url=base_url,
    )


__all__ = [
    "FakeMetaCloudClient",
    "FakeResponseRegistry",
    "FakeWahaClient",
    "InMemoryLidPhoneCache",
    "InMemoryWebhookDedup",
    "InboundHandler",
    "LidPhoneCache",
    "META_CLOUD_DEFAULT_BASE_URL",
    "MetaCloudClient",
    "PersistentResponseRegistry",
    "RedisLidPhoneCache",
    "RedisWebhookDedup",
    "ResponseRegistry",
    "ResponseSample",
    "ResponseSampleSink",
    "SetnxRedis",
    "WahaClient",
    "WahaIgnoredEvent",
    "WahaSessionNotReady",
    "WahaInboundMessage",
    "WahaMedia",
    "WahaPayloadError",
    "WebhookDedup",
    "WhatsAppClient",
    "WhatsAppIgnoredEvent",
    "WhatsAppInboundMessage",
    "WhatsAppMedia",
    "WhatsAppPayloadError",
    "WhatsAppSettings",
    "build_send_text_body",
    "chat_id_for_phone",
    "create_whatsapp_webhook_router",
    "extract_resolved_remote",
    "fingerprint_response",
    "get_lid_phone_cache",
    "get_meta_cloud_client",
    "get_response_registry",
    "get_webhook_dedup",
    "get_whatsapp_client",
    "is_authorized",
    "is_lid",
    "is_phone_jid",
    "normalize_phone",
    "parse_waha_inbound_message",
    "phone_from_chat_id",
    "remember_lid_phone",
    "resolve_canonical_session",
    "rewrite_vendor_media_url",
]
