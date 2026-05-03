"""WhatsApp connector — WAHA inbound parser + outbound sender + webhook router.

Lifted from `whatsapp-google-scheduling/app/services/waha/` 2026-05-03
via `projects/whatsapp-seed-absorption/`. Provider-neutral by design —
swapping to Twilio / Cloud API later does not rename the public surface.

Public surface:
- Types: `WhatsAppInboundMessage`, `WhatsAppMedia`, `WhatsAppPayloadError`,
  `WhatsAppIgnoredEvent`. Legacy `Waha*` aliases preserved.
- Parsing: `parse_waha_inbound_message`, `chat_id_for_phone`,
  `phone_from_chat_id`, `build_send_text_body`.
- HTTP: `WahaClient` (sync + async send_text + download_media).
- FastAPI: `create_whatsapp_webhook_router` factory.
- Settings: `WhatsAppSettings` Pydantic model.

See `KB § PATTERNS/whatsapp-chatbot-seed.md` for the wiring recipe
(forthcoming via Phase 9 of `whatsapp-seed-absorption`).
"""

from noctusai_lib.integrations.whatsapp.client import WahaClient
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
    WhatsAppIgnoredEvent,
    WhatsAppInboundMessage,
    WhatsAppMedia,
    WhatsAppPayloadError,
)

__all__ = [
    "InboundHandler",
    "WahaClient",
    "WahaIgnoredEvent",
    "WahaInboundMessage",
    "WahaMedia",
    "WahaPayloadError",
    "WhatsAppIgnoredEvent",
    "WhatsAppInboundMessage",
    "WhatsAppMedia",
    "WhatsAppPayloadError",
    "WhatsAppSettings",
    "build_send_text_body",
    "chat_id_for_phone",
    "create_whatsapp_webhook_router",
    "parse_waha_inbound_message",
    "phone_from_chat_id",
]
