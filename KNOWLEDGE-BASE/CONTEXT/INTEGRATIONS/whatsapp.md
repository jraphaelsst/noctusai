# WhatsApp connector — consume-side reference

> **Purpose.** Authoritative consume-side reference for
> `noctusai_lib.integrations.whatsapp` — the seed's provider-neutral
> WhatsApp connector: WAHA inbound parser + outbound sender + webhook
> router + @lid auth + dedup + Meta Cloud API client. Folds **what
> ships** (verified against `__all__`), **consume recipe** (import ->
> factory -> webhook-router mount via NAMED seams, real consumer cited
> `path:line`), **the two backends** (WAHA self-hosted vs Meta Cloud
> API), and **gaps** into one durable doc.
>
> **Why this lives in KB.** Project folders
> (`whatsapp-seed-absorption/`, `social-wiring-absorption/`) are
> deleted at close; this doc is durable and self-contained. The wiring
> *recipe* (chatbot composition: buffer + worker + LLM dispatcher) is
> at `CONTEXT/PATTERNS/whatsapp-chatbot-seed.md`; THIS doc is the
> connector API surface a product imports.
>
> **Provider-neutral by design.** Swapping WAHA -> Twilio -> Cloud API
> later does not rename the public surface. Provenance: lifted from
> `whatsapp-google-scheduling/app/services/waha/` 2026-05-03
> (`whatsapp-seed-absorption/`); reconciled 2026-05-16 to the
> live-validated `noctusai-youtube-crawler` workspace (LID-auth +
> dedup + media-URL rewrite) via `social-wiring-absorption/` Wave 1.E2.

---

## 1. What ships — exact `__all__`

Package: `seed/lib/backend/noctusai_lib/integrations/whatsapp/`.
Every symbol below is exported from `whatsapp/__init__.py.__all__`.

### Inbound types + parsing (`whatsapp.types` / `.mappers`)
| Symbol | Role |
|---|---|
| `WhatsAppInboundMessage` `WhatsAppMedia` | Parsed inbound message + media (canonical names) |
| `WhatsAppPayloadError` `WhatsAppIgnoredEvent` | Typed parse failure / non-message event |
| `WhatsAppClient` | Protocol — the send/download contract |
| `WahaInboundMessage` `WahaMedia` `WahaPayloadError` `WahaIgnoredEvent` | Legacy `Waha*` aliases preserved |
| `parse_waha_inbound_message` | WAHA webhook body -> `WhatsAppInboundMessage` |
| `chat_id_for_phone` `phone_from_chat_id` | Phone <-> WAHA `@c.us` chat-id |
| `build_send_text_body` `rewrite_vendor_media_url` | Outbound body builder; external->internal media-URL rewrite |

### HTTP clients + factories
| Symbol | Role |
|---|---|
| `WahaClient` | Real WAHA client (sync + async `send_text` + `download_media`) |
| `FakeWahaClient` | Bi-directional in-memory deterministic — records `sent_messages`, accepts `inject_text`/`inject_inbound`, serves `media_bytes` |
| `get_whatsapp_client(...)` | **Factory** — `WahaClient` when `base_url=` set, else `FakeWahaClient` |
| `MetaCloudClient` `FakeMetaCloudClient` | Meta Cloud API (WhatsApp Business) client + fake |
| `get_meta_cloud_client(...)` | **Factory** — `MetaCloudClient` when `api_key=` set, else `FakeMetaCloudClient` |
| `META_CLOUD_DEFAULT_BASE_URL` | Default Cloud API base |

### @lid auth (`whatsapp.lid_auth`)
`is_authorized` (3-tier), `resolve_canonical_session`,
`remember_lid_phone`, `get_lid_phone_cache`,
`LidPhoneCache`/`InMemoryLidPhoneCache`/`RedisLidPhoneCache`
(Protocol+Fake+Real), plus pure helpers `is_lid`, `is_phone_jid`,
`normalize_phone`, `extract_resolved_remote`.

### Webhook dedup (`whatsapp.dedup`)
`WebhookDedup` Protocol + `RedisWebhookDedup` (SETNX pre-filter) +
`InMemoryWebhookDedup` + `get_webhook_dedup` + `SetnxRedis`. The DB
UNIQUE backstop is the chatbot `message_store` seam — consumer
composes both.

### Response-shape registry (`whatsapp.response_registry`)
`ResponseRegistry` Protocol + `FakeResponseRegistry` +
`PersistentResponseRegistry` + `get_response_registry` +
`ResponseSample` / `ResponseSampleSink` / `fingerprint_response`
(WAHA drift observability side-car).

### FastAPI seam + settings
| Symbol | Role |
|---|---|
| `create_whatsapp_webhook_router(..., dedup=)` | Webhook-receiver router factory |
| `InboundHandler` | The handler protocol the router invokes per inbound message |
| `WhatsAppSettings` | Pydantic settings model |

---

## 2. Consume recipe

```python
from noctusai_lib.integrations.whatsapp import (
    get_whatsapp_client, create_whatsapp_webhook_router, get_webhook_dedup,
)

client = get_whatsapp_client(
    base_url=waha_url, api_key=waha_key, session=session,
)                                  # WahaClient or FakeWahaClient
data = await client.send_text(chat_id, message)
```

`base_url=` set => `WahaClient`; unset => `FakeWahaClient`
(configured-vs-not signal, mirrors `get_calendar_adapter()` per
`CONTEXT/PATTERNS/seed-fake-real-adapter.md`). `external_base_url=`
is the browser-facing host WAHA *emits* in media URLs vs `base_url`
the docker-internal host the app *reaches* (defaults to `base_url` —
single-host dev rewrite is a no-op).

**Webhook router via the standard-routers NAMED seam** — the
product's `create_product_app(...)` mounts
`create_whatsapp_webhook_router(handler=..., dedup=get_webhook_dedup(...))`;
never hand-register the receiver. Dedup is injected, not hard-wired.

**Live consumers (cited):**

- `products/erp-imobiliario/backend/app/services/whatsapp_service.py:336`
  — `from noctusai_lib.integrations.whatsapp import get_whatsapp_client`;
  `:338` `client = get_whatsapp_client(base_url=waha_url,
  api_key=waha_key, session=session)`. Thin ERP wrapper owning
  ERP-specific concerns (phone normalization, CRM error envelope).
- `products/erp-imobiliario/backend/app/services/whatsapp_service.py:196`
  — second backend: `from noctusai_lib.integrations.whatsapp import
  get_meta_cloud_client` (WhatsApp **Business Cloud API** path).

The full chatbot composition (Redis buffer -> worker -> LLM dispatcher)
is the recipe at `CONTEXT/PATTERNS/whatsapp-chatbot-seed.md`.

---

## 3. The two backends

| | `WahaClient` (`get_whatsapp_client`) | `MetaCloudClient` (`get_meta_cloud_client`) |
|---|---|---|
| Transport | Self-hosted **WAHA** (WhatsApp HTTP API) | Official **Meta Cloud API** (WhatsApp Business) |
| Configured signal | `base_url=` set | `api_key=` (Bearer) set |
| Fake fallback | `FakeWahaClient` | `FakeMetaCloudClient` |
| Identity | WAHA session (`@c.us` chat-ids) | `phone_number_id` |

Both factories follow the seed Fake+Real shape. Provider-neutral
public names mean the chatbot framework consumes `WhatsAppClient`
without caring which backend is wired.

---

## 4. Errors

`WahaClient` raises `httpx.HTTPStatusError` on non-2xx
(`raise_for_status`) — consumers map to their own error envelope
(ERP wrapper does this at `whatsapp_service.py:340+`). Parse failures
surface as typed `WhatsAppPayloadError`; non-message webhook events as
`WhatsAppIgnoredEvent` (not errors — the router skips them).

---

## 5. Gaps / out-of-scope (with destinations)

| Item | Status | Destination |
|---|---|---|
| Twilio backend | not shipped | Provider-neutral surface is ready; add `integrations/whatsapp/twilio_client.py` + factory branch when a consumer needs it |
| Outbound media send (image/doc) | partial — `send_text` + `download_media` ship; rich outbound media is not in the Protocol | Additive Protocol extension; file when a consumer needs it |
| Chatbot orchestration (buffer/worker/LLM dispatch) | **separate by design** | `noctusai_lib.domain.chatbot` + recipe `CONTEXT/PATTERNS/whatsapp-chatbot-seed.md` |
| FB Pages / Instagram Graph | **separate package** | `noctusai_lib.integrations.meta` — `CONTEXT/INTEGRATIONS/meta.md` |
