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
> at `CONTEXT/PATTERNS/backend/whatsapp-chatbot-seed.md`; THIS doc is the
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
| `WahaClient` | Real WAHA client (sync + async `send_text` + `download_media`); every call routes through `_request`/`_request_sync`, paced against the shared `"whatsapp"` rate-limit bucket; `transport=` constructor param (an `httpx.MockTransport`) is the test seam — no monkey-patching needed |
| `FakeWahaClient` | Bi-directional in-memory deterministic — records `sent_messages`, accepts `inject_text`/`inject_inbound`, serves `media_bytes` |
| `get_whatsapp_client(...)` | **Factory** — `WahaClient` when `base_url=` set, else `FakeWahaClient` |
| `MetaCloudClient` `FakeMetaCloudClient` | Meta Cloud API (WhatsApp Business) client + fake — 1:1 only, does **not** implement `WhatsAppGroupClient` |
| `get_meta_cloud_client(...)` | **Factory** — `MetaCloudClient` when `api_key=` set, else `FakeMetaCloudClient` |
| `META_CLOUD_DEFAULT_BASE_URL` | Default Cloud API base |

### Group management (`whatsapp.types` / `.mappers` / `.client`)
| Symbol | Role |
|---|---|
| `WhatsAppGroupClient` | Protocol — separate from `WhatsAppClient` so a 1:1-only connector isn't forced to implement it. `WahaClient` + `FakeWahaClient` satisfy it |
| `GroupInfo` `GroupParticipant` `ParticipantChangeResult` | Value types — a group, one member (`role: participant\|admin\|superadmin`), one add/remove outcome (`outcome: added\|removed\|invite_required\|failed`) |
| `WahaGroupError` | Typed error for a group op that failed for a real (non-privacy-refusal) reason — carries `op` + `status`; alongside `WahaSessionNotReady` |
| `create_group` `list_groups` `get_group` `list_participants` `add_participants` `remove_participants` `promote_admins` `demote_admins` `get_invite_link` `revoke_invite_link` `set_messages_admin_only` `delete_message` `leave_group` | `WahaClient`/`FakeWahaClient` methods — the full `WhatsAppGroupClient` surface |

Broadcast to an existing group needs nothing new: `send_text` already
accepts a `@g.us` chat id. A group INBOUND message additionally
populates `WhatsAppInboundMessage.group_id` (the `@g.us` chat id) and
`.author_id` (the sending participant's JID, from WAHA's `participant`/
`author` field) — both additive, default `None`; `from_phone`/`chat_id`
keep their pre-existing shape (`from_phone` still names the GROUP on a
group message, not the author — a known gap this addition does not
close).

**Endpoint verification + engine finding (Slice W, 2026-09-16):**
endpoint paths/body shapes match the WAHA Groups API's documented
`/api/{session}/groups...` convention (this client's own established
shape) and this session's design spec — **not independently
re-verified against a live WAHA swagger fetch**: neither the `waha`
MCP server's tools nor outbound web access were bound to this dispatch,
and a live-VPS read was denied by the session's permission classifier.
Static evidence confirms the fleet's configured engine: `WHATSAPP_DEFAULT_ENGINE:
NOWEB` (`deploy/services/compose.services.yml:113`), image
`devlikeapro/waha:latest` — **unpinned**, a pre-existing risk this slice
did not touch (`deploy/` is out of scope here). WAHA's Groups API has
historically shipped on the NOWEB engine at the Core (self-hosted,
free) tier this fleet runs.

**Live confirmation (tech-lead, 2026-09-16, `waha.server.version`):** the
running server reports `version=2026.7.2`, `engine=NOWEB`, `tier=CORE`,
`platform=linux/x64`. That matches the static evidence above, so the group
endpoints this slice targets are the NOWEB/CORE set. The per-participant
response shape is still un-exercised against a real group (no write call was
made), which is what `NOC-REMEDIATE[waha-verify]` tracks.
See `NOC-REMEDIATE[waha-verify]` in
`noctusai_lib/integrations/whatsapp/mappers.py`
(`participant_change_result_from_waha`) for the specific per-participant
status-code assumption (`401`/`403` → `"invite_required"`) that most
needs a live confirmation before this carries production bulk-add
traffic.

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
`CONTEXT/PATTERNS/backend/seed-fake-real-adapter.md`). `external_base_url=`
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
is the recipe at `CONTEXT/PATTERNS/backend/whatsapp-chatbot-seed.md`.

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
`WhatsAppIgnoredEvent` (not errors — the router skips them). Group ops
raise `WahaGroupError` (op + status; wraps the original
`HTTPStatusError` as `__cause__`) instead of a bare `httpx` error —
**except** `add_participants`/`remove_participants`, which never raise
for a per-participant refusal: that outcome is reported per-id via
`ParticipantChangeResult(outcome="invite_required"|"failed")` instead.

---

## 4a. 🔴 Session config is a REPLACE, and WAHA's keys are camelCase

Two traps that have each cost real production time. Both are structural, so the
cure is structural: **no caller hand-assembles a session config** — every
config-writing path routes through `client._session_config()`.

- **`PUT /api/sessions/{name}` is a full config REPLACE, not a merge.** Any key
  you omit is DROPPED. A partial `set_webhook` PUT once clobbered the
  `noweb.store` block that `start_session` had set, so the engine kept no
  history and `GET /api/{session}/chats` began 400-ing (2026-06-23, empty-inbox
  incident).
- **WAHA's store key is camelCase `fullSync`, not `full_sync`.** The client sent
  the snake_case spelling for weeks; WAHA silently ignored the unknown key and
  applied the default (`false`), so NOWEB **never backfilled history** while the
  code looked correct and the tests were green — two of them asserted the buggy
  key, making the false-green self-reinforcing. Fixed 2026-08-03.
  - Detection that actually works: assert the **emitted wire key**
    (`"fullSync" in payload["config"]["noweb"]["store"]`) *and* the absence of
    the wrong one. A test that reads back your own dict proves nothing about
    what the vendor accepted.
  - Verification signal: after a fresh pairing, `GET /api/sessions/{name}` must
    report `"fullSync": true`. If it reports `false`, the value was dropped.
  - Generalize: for any vendor config you PUT and never read back, the vendor's
    own echo is the only proof it landed.
- `fullSync` backfills history **at authentication**, so only a FRESH pairing
  (`logout` → `start` → scan) populates existing chats. Restarting an
  already-paired session will not re-pull history.

## 5. Gaps / out-of-scope (with destinations)

| Item | Status | Destination |
|---|---|---|
| Twilio backend | not shipped | Provider-neutral surface is ready; add `integrations/whatsapp/twilio_client.py` + factory branch when a consumer needs it |
| Outbound media send (image/doc) | partial — `send_text` + `download_media` ship; rich outbound media is not in the Protocol | Additive Protocol extension; file when a consumer needs it |
| MCP-surfaced group tools (`waha.group.*`) | not shipped — `WahaClient`/`FakeWahaClient` ship the group surface, `mcp/waha` does not yet expose it | Slice W2 (deliberately deferred, wave0-design.md): `mcp/waha/tools/groups.py`, mirroring the existing `session`/`message`/`server` tool modules |
| Live confirmation of WAHA group-endpoint wire shapes | inferred from the WAHA Groups API's documented convention, not fetched from a live swagger this pass (no `waha` MCP / web access bound to this dispatch, live-VPS read denied) | Re-verify against `GET /api/server/version` + the live swagger (`waha.server.version` MCP tool, or `/api` on a bound session) before group ops carry real traffic; see `NOC-REMEDIATE[waha-verify]` in `mappers.py` |
| `devlikeapro/waha:latest` unpinned in `deploy/` | pre-existing, untouched by this slice (group endpoints differ by engine: WEBJS/NOWEB/GOWS — fleet runs NOWEB) | `deploy/services/compose.services.yml:106` / `deploy/fleet/compose.infra.prod.yml:109` — pin when a devops slice is scheduled |
| Read-state INBOUND (phone → app) | **not expressible with this transport** | `message.ack` carries acks only for messages WE sent; `chats/overview`'s `ChatSummary` (`{id,name,picture,lastMessage,_chat}`) has no top-level `unreadCount`. `sendSeen` therefore syncs read state OUT to the device, but reading a chat ON the phone does not clear the app's badge. Probe the untyped `_chat.unreadCount` once a session is `WORKING` if this needs revisiting. |
| Realtime delivery to the browser | shipped, but **not in this package** | `noctusai_lib.realtime` (SSE + Redis Streams) → `CONTEXT/PATTERNS/common/realtime-sse-bus.md` |
| Chatbot orchestration (buffer/worker/LLM dispatch) | **separate by design** | `noctusai_lib.domain.chatbot` + recipe `CONTEXT/PATTERNS/backend/whatsapp-chatbot-seed.md` |
| FB Pages / Instagram Graph | **separate package** | `noctusai_lib.integrations.meta` — `CONTEXT/INTEGRATIONS/meta.md` |
