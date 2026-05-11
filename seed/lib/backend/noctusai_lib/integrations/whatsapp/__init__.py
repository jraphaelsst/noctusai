"""WhatsApp connector — WAHA inbound parser + outbound sender + webhook router.

Lifted from `whatsapp-google-scheduling/app/services/waha/` 2026-05-03
via `projects/whatsapp-seed-absorption/`. Provider-neutral by design —
swapping to Twilio / Cloud API later does not rename the public surface.

Public surface:
- Types: `WhatsAppInboundMessage`, `WhatsAppMedia`, `WhatsAppPayloadError`,
  `WhatsAppIgnoredEvent`, `WhatsAppClient` Protocol. Legacy `Waha*`
  aliases preserved.
- Parsing: `parse_waha_inbound_message`, `chat_id_for_phone`,
  `phone_from_chat_id`, `build_send_text_body`.
- HTTP: `WahaClient` (sync + async send_text + download_media).
- Fake: `FakeWahaClient` — bi-directional in-memory deterministic
  (records `sent_messages`, accepts `inject_text` / `inject_inbound`,
  serves pre-populated `media_bytes`).
- Factory: `get_whatsapp_client(base_url=, api_key=, session=)` —
  returns `WahaClient` when `base_url` is set, `FakeWahaClient` otherwise.
  Mirrors `google_calendar.get_calendar_adapter()` and
  `google_maps.get_routing_adapter()` per
  `KB § PATTERNS/seed-fake-real-adapter.md`.
- FastAPI: `create_whatsapp_webhook_router` factory.
- Settings: `WhatsAppSettings` Pydantic model.

See `KB § PATTERNS/whatsapp-chatbot-seed.md` for the wiring recipe.
"""

from noctusai_lib.integrations.whatsapp.client import WahaClient
from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
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
) -> WhatsAppClient:
    """Return a real WAHA client when `base_url` is set; `FakeWahaClient` otherwise.

    Mirrors `get_calendar_adapter()` and `get_routing_adapter()` shape per
    `KB § PATTERNS/seed-fake-real-adapter.md`. The presence of `base_url`
    is the configured-vs-not-configured signal — a real WAHA endpoint
    means we're talking to a real server.
    """
    if not base_url:
        return FakeWahaClient(session=session)
    return WahaClient(base_url=base_url, api_key=api_key, session=session)


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
    "FakeWahaClient",
    "InboundHandler",
    "META_CLOUD_DEFAULT_BASE_URL",
    "MetaCloudClient",
    "WahaClient",
    "WahaIgnoredEvent",
    "WahaInboundMessage",
    "WahaMedia",
    "WahaPayloadError",
    "WhatsAppClient",
    "WhatsAppIgnoredEvent",
    "WhatsAppInboundMessage",
    "WhatsAppMedia",
    "WhatsAppPayloadError",
    "WhatsAppSettings",
    "build_send_text_body",
    "chat_id_for_phone",
    "create_whatsapp_webhook_router",
    "get_meta_cloud_client",
    "get_whatsapp_client",
    "parse_waha_inbound_message",
    "phone_from_chat_id",
]
