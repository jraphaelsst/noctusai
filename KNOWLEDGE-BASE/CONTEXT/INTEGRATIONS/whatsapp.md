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

### Identity resolution (`whatsapp.identity`)
| Symbol | Role |
|---|---|
| `resolve_identity(client, raw_jid)` | Async — resolves any raw JID (`@c.us` / `@s.whatsapp.net` / `@lid`) to a canonical `ResolvedIdentity` keyed on phone digits, not the LID; fail-soft (a WAHA error yields a partial result, never a raise) |
| `ResolvedIdentity` | Value type — `phone`, `jid`, `lids: list[str]`, `name` |
| `build_lids_map_from_list(lids_list)` | One-shot `{lid_jid: phone_digits}` map from `list_lids()` output — avoids N WAHA calls per chat during a bulk dedup pass |

See § 4b for the 2026-09-17 promotion of this module from `social-wiring` to the seed.

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

### Multi-session connection store (`whatsapp.connection_store`)
| Symbol | Role |
|---|---|
| `WhatsAppConnectionRecord` | One connection "line" (id, org_id, user_id=creator provenance, label, base_url, session_name, webhook_url/token, `extra` extension dict) |
| `WhatsAppConnectionStore` | CRUD over `<schema>.<table>` — field-level Fernet encryption of the API key. `record_extension=` hook folds product-specific columns into `.extra`; `extra_fields=` on `create_connection`/`update_connection` writes them |
| `build_whatsapp_connection_store(client, *, encryption_key, schema, table=, record_extension=)` | Factory — validates `ENCRYPTION_KEY` loudly via `noctusai_lib.security.api_keys.require_fernet` (the SAME check the api-keys store uses) |
| `resolve_by_webhook_token(store, token)` | Named seam for a product's own `POST .../webhook/{token}` handler — thin pass-through to `store.get_by_webhook_token`, kept as one call site for the "never log the token; unknown -> generic 404" contract |
| `whatsapp_connections_table_ddl(schema, *, table=)` | DDL-template helper (org-scoped RLS + service-role bypass) — a product copies the emitted SQL into its own migration |
| `WhatsAppConnectionStoreError` | Decrypt failure (`ENCRYPTION_KEY` mismatch / tampered ciphertext) — fail-loud, never a silent `None` |

Lifted 2026-09-17 (`community uses social-wiring's mechanisms`, Slice A)
from `social-wiring`'s `app/services/whatsapp_connection_store.py` — CORE
columns only (org_id/user_id/label/base_url/session_name/
encrypted_api_key/webhook_url/webhook_token). `social-wiring`'s own
`auto_reply_enabled` / `authorized_numbers` / `bound_chats` / `marca_id`
columns stay product-local, reachable via `record_extension`/
`extra_fields` rather than this module growing product-specific columns.
`social-wiring` itself is unmodified by this lift (see the
`NOC-REMEDIATE[sw-consume-seed-wa-connections]` marker at the top of its
store module — it migrates to consume this seam in a later slice).

The paired FastAPI router factory —
`noctusai_seed.whatsapp_connections_router.create_whatsapp_connections_router(deps, settings, *, store_factory, get_current_user_org, waha_base_url, resolve_webhook_base_url, ...)`
— ships the full `social-wiring` `/api/whatsapp/connections` CRUD +
live-WAHA-ops contract (list/create/update/delete, `/status`, `/qr`,
`/start`, `/restart`, `/logout`, `/recover`, `/webhook`) over this store.
It is NOT a `_STANDARD_ROUTERS` entry (product-specific parameters don't
fit the fixed builder signature — same as `auth`'s direct-call path, see
`CONTEXT/03-SEED-ARCHITECTURE.md § Standard routers`) and supersedes the
removed single-session `whatsapp_admin` standard router. Chat inbox /
message threads / SSE / auto-reply toggle stay product-specific (chatbot
concerns, not a generic connection-management mechanism) — see § 5 Gaps.

### Managed API keys (`noctusai_lib.security.api_keys` — sibling package)
The org-scoped, operator-managed key store (`ApiKeySpec`/`ApiKeyOption`,
`build_api_key_store`, `resolve_api_key`/`resolve_api_key_detail`,
`make_local_credential_override`, `require_fernet`/
`EncryptionNotConfigured`) that shares its Fernet-key contract with the
connection store above lives in `noctusai_lib.security.api_keys`, not
this package (it is provider-agnostic — OpenAI/Anthropic/Gemini/
InfoSimples keys, not a WhatsApp concern). Paired router factory:
`noctusai_seed.api_keys_router.create_api_keys_router(...)`. Lifted the
same slice, from `social-wiring`'s `app/services/api_keys_store.py` +
`app/services/credential_vault.py`.

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
- **A session can serve several products — `set_webhook` MERGES.** Because the
  PUT replaces the whole `config.webhooks` list, a naive write by product B
  silently dropped product A's webhook on a shared session. `set_webhook(url,
  events, *, owned_prefix=None)` therefore GETs the current list, drops only
  its own entries (`url` exactly, or `owned_prefix` — default: `url` minus its
  last path segment; exact-match-only when no path would remain), appends the
  new entry and PUTs the merged list (foreign `hmac`/`retries`/`customHeaders`
  verbatim, NOWEB store block still re-asserted). A re-registration with a new
  token replaces that product's old token URL. `remove_webhook(url_or_prefix)`
  is the symmetric remove (no PUT / no restart when nothing matches). If the
  GET fails or is malformed both raise `WahaWebhookError` — never a blind
  replace. The seed connections router calls `remove_webhook` on DELETE
  (best-effort, ERROR-logged on failure; no logout).
  The rest of the config is carried forward too (`_merged_session_config`).
  Only `webhooks` changes; the session owner's other keys stay as set
  (`noweb.markOnline`, `store.fullSync`, `metadata`, …). `store.enabled` is
  forced on, and `fullSync` defaults to `true` only when absent. Rebuilding
  from `_session_config` defaults would have flipped the shared prod session's
  `markOnline: true, fullSync: false` (found 2026-10-15, before orbity first
  connected).
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

## 4b. Identity-resolver seed promotion + group rate-limit bucket (2026-09-17)

**Lift.** `resolve_identity` / `ResolvedIdentity` / `build_lids_map_from_list`
moved from `products/social-wiring/backend/app/services/whatsapp_identity.py`
to `noctusai_lib.integrations.whatsapp.identity` (part of the `community`
module 3 seed slice — the tables/endpoints landing in `community` itself are
a separate, later slice). The module was already pure WAHA shape with zero
social-wiring domain (it imported only `lid_auth.is_lid` / `normalize_phone`),
so the move is a straight file relocation, no rewrite. Both are exported from
`whatsapp/__init__.py`'s `__all__` per § 1 above.

**Shim.** social-wiring is a LIVE product, so its own
`app/services/whatsapp_identity.py` is now an explicit-name re-export shim
(`from noctusai_lib.integrations.whatsapp.identity import ResolvedIdentity,
build_lids_map_from_list, resolve_identity`) — not a star-import, so a
type-checker/IDE still resolves the exact names. Byte-equivalent runtime
behaviour: `app/routers/whatsapp_router.py`'s `from app.services.whatsapp_identity
import resolve_identity` and the product's own
`tests/services/test_whatsapp_identity.py` are untouched and still pass
against the shim. The shim is **deletable in a later, separate step** once
social-wiring's call sites are re-pointed directly at the seed module — not
done in this slice, to keep it a pure lift with zero call-site churn.

**New rate-limit bucket.** `noctusai_lib.integrations.rate_limit._DEFAULTS`
gained `"whatsapp_groups": BucketConfig(rate_per_sec=0.2, burst=1)`, purely
additive — the existing `"whatsapp"` bucket (5 rps / burst 10, tuned for
1:1 messaging) is far too hot for group administration (add/remove
participant, invite-link get/revoke); pacing bulk participant adds at 5 rps
is the WhatsApp-ban vector `community`'s ban-risk posture calls out. Every
group-mutating call must route through
`rate_limit.acquire_async("whatsapp_groups")`, never `"whatsapp"`.

**Two-sessions note, for whoever wires a second WAHA session.** The WAHA
instance's default `WHATSAPP_HOOK_URL` in
`deploy/services/compose.services.yml` points inbound at **n8n**. A session
that never calls `set_webhook` explicitly therefore delivers its messages to
n8n silently — there is no error, no log line calling this out, just traffic
arriving at the wrong consumer. Live-verified 2026-09-17: WAHA `2026.7.2`,
engine NOWEB, tier CORE, exactly one session (`default`, `WORKING`) whose
webhook already points at social-wiring. Tier CORE is single-session, so a
product needing its own line (e.g. `community`, per its module-3 D4 decision)
needs its own `waha-*` container + its own explicit `set_webhook` call — never
assume the default session's webhook target is inherited.

## 4c. Brazilian 9th-digit resolution (2026-10)

BR mobiles exist on WhatsApp with or without the 9th digit (older accounts: `55 DD` + 8 digits). Built once in the seed:

- `primitives.phone.br_mobile_variants(raw)` -> ordered bare-digit candidates (as-given first, then the with/without-9 variant; landlines and foreign numbers untouched; junk -> `[]`).
- `WahaClient.check_exists(phone)` (GET `/api/contacts/check-exists?phone=&session=`), `resolve_chat_id(phone) -> ResolvedChat` (per-process 10-min cache), `send_text_to_phone(phone, text)`.
- Result = WAHA send result + `resolvedChatId`, `resolvedVariantUsed`, `resolutionMethod` (`check-exists` | `send-retry`). The caller decides whether to persist; the seed NEVER rewrites stored contact data.
- Errors: `WahaNumberNotOnWhatsApp(tried)` (no spelling registered), `WahaNumberCheckError` (check endpoint unavailable -> `send_text_to_phone` falls back to send-then-retry across variants).
- `FakeWahaClient.registered_numbers` / `check_unavailable` mirror it. `send_text(chat_id, ...)` is unchanged (backward compatible).

## 4d. Inbox organ — read + reply conversations (2026-10-26)

The conversations pipeline `social-wiring` grew (chat list, thread, reply, unread, backfill, realtime) lifted to the seed WITHOUT its Julia / chatbot / auto-reply / lead-intake behaviour. First consumer: `monica` (pilot #1). Sits on top of the QR organ (§4: `whatsapp_connections_router` + `connection_store`) — one connection = one WAHA line.

| Piece | Where | What |
|---|---|---|
| DDL | `noctusai_lib.integrations.whatsapp.inbox` | `whatsapp_chats_table_ddl(schema)` (PK `(connection_id, chat_id)`, FK to connections ON DELETE CASCADE, `origin`, `new_chat_notified_at`) + `whatsapp_messages_table_ddl(schema)` (`UNIQUE (connection_id, waha_message_id)` = the dedup guard). Authoring-time helpers like `whatsapp_connections_table_ddl`. |
| Store | same | `WhatsAppChatStore` Protocol · `FakeWhatsAppChatStore` · `SupabaseWhatsAppChatStore` · `build_whatsapp_chat_store(client, schema=, allow_fake=False)` — **fake-or-refuse**: no client and no explicit `allow_fake` raises `InboxStoreNotConfigured`. |
| Ingest | same | `ingest_waha_event(body, connection=, chat_store=, realtime=, on_new_chat=, lid_cache=, waha_client_factory=)`: `message` / `message.any` / `message.ack` / `session.status`. |
| Backfill | same | `backfill_connection` / `run_backfill_all` / `register_inbox_backfill_job` (seed scheduler). |
| Realtime | same | `build_inbox_realtime(redis_client= \| redis_url= \| allow_in_process=True)` over `noctusai_lib.realtime`; events `message.new`, `chat.upsert`, `message.ack`, `chat.read`, `session.status` on scope `wa:conn:{connection_id}`. |
| Router | `noctusai_seed.whatsapp_inbox_router.create_whatsapp_inbox_router` | `GET .../chats`, `GET\|POST .../chats/{chat_id}/messages`, `POST .../chats/{chat_id}/read`, `POST .../backfill`, `GET .../events` (SSE) + the PUBLIC webhook. |
| Frontend | `@noctusai/lib` | `createWhatsAppInboxHooks(api, {getAuthToken})` + `<WhatsAppInbox hooks connectionId initialChatId renderChatHeaderExtra/>` (organ `components/whatsapp-inbox/`, on the seed `ChatWindow`). |

**Consume recipe (backend).** Mount the connections router AND the inbox router; the webhook path must be the same value in both (`webhook_path_prefix`, default `/api/whatsapp/webhook`) because the connections router MINTS `{product_url}{prefix}/{token}` and registers it on WAHA, and the inbox router RECEIVES on `{prefix}/{token}` (`test_webhook_path_matches_minted_url` pins the round trip). Pass `on_new_chat=lead_service.upsert_from_whatsapp` to turn a new contact into a lead, and `on_message=` (optional; `ingest_waha_event` AND the router's send path) to react to EVERY newly stored message, inbound or outbound — e.g. `LeadsService.touch_last_message` to keep a card's preview fresh. `on_message(org_id, connection_id, chat, message)` is best-effort (a raising consumer is logged, never fails the webhook/send), fires only for a message that was actually inserted (a duplicate or the `message`/`message.any` echo does not re-fire) and never for backfilled history. Reference consumer: `products/monica/backend/app/services/whatsapp_leads.py`.

**Contracts worth knowing**

- **`on_new_chat(org_id, connection_id, chat)` fires exactly once** per chat row first created by an INBOUND message to a NON-group chat. The decision is an atomic conditional UPDATE (`claim_new_chat_notification`) on the chat row — so a replayed webhook, the `message` + `message.any` pair, concurrent deliveries, and deleting the downstream lead (the chat row persists) can never fire it twice. Chats created by an outbound message or by backfill never fire. A consumer that raises releases the claim; the next inbound message of that chat retries (so the consumer must be idempotent — e.g. UNIQUE `(org, connection, chat)` on leads).
- **Dedup is the DB.** No Redis/in-memory pre-filter: a duplicate costs one cheap UNIQUE-conflict insert. The webhook returns 5xx on a store failure (WAHA retries; the retry is idempotent) and 200 for payloads it cannot parse.
- **@lid.** A `@lid` chat is canonicalised to `<phone>@c.us` through the seed `LidPhoneCache` (then `resolve_identity` over WAHA, fail-soft); unresolved stays `@lid` with `phone = null`. Chat ids are never rebuilt from a sender field (`fromMe` -> `to`, inbound -> `from`; a group's `participant` is the SENDER, not the chat). A chat stored under an `@lid` id before its phone resolved is NOT merged retroactively.
- **Unread is recomputed** (inbound messages newer than `last_read_at`), never incremented. Backfilled chats start read.
- **Pagination.** Chats: opaque `next_cursor`. Messages: pages are chronological, `before` = `<iso>|<id>` of the oldest held (WAHA timestamps have 1 s resolution — a bare timestamp cursor loses ties).
- **Send** goes through the `WahaClient`, which paces every request on the shared `"whatsapp"` token bucket (`integrations.rate_limit`); a connection with no `base_url` is refused (503) rather than handed the Fake client.
- **Webhook auth.** Path token (unknown -> generic 404, never logged) + `X-Webhook-Hmac-SHA256` when `webhook_hmac_secret` is set. The seed `set_webhook` registers `hmac: None` per webhook, so WAHA only signs if it runs with a global `WHATSAPP_HOOK_HMAC_KEY` — set the same value on the product.

**Traps**

1. **NOWEB store.** Backfill needs `list_chats` / `fetch_chat_messages`, which only work on a session started with `store.enabled` + `fullSync` (the seed start/restart does that). WAHA answers HTTP 400 otherwise -> report status `noweb_store_required`.
2. **Backfill single-flight is per process.** An in-memory set + the scheduler's `max_instances=1`; with >1 worker/replica each process may backfill the same connection. Safe (UNIQUE makes inserts idempotent), wasteful. `NOC-REMEDIATE[wa-inbox-backfill-distributed-lock]`.
3. **Backfill is one-shot per chat** (`synced_through`): `fetch_chat_messages` has no `before=` cursor.
4. **Realtime is per process unless Redis.** `allow_in_process=True` is a declared single-worker decision; neither it nor Redis -> `InboxRealtimeNotConfigured`.
5. **Media URLs are WAHA's own** (browser-unreachable behind the docker network): stored as given; a media proxy is not in v1.
6. **Mark-read does not touch the phone** unless `mirror_read_to_whatsapp=True` (WAHA `sendSeen` = blue ticks for the contact).

`NOC-REMEDIATE[sw-consume-seed-wa-inbox]`: `social-wiring` keeps its own copy of this pipeline (`whatsapp_chat_store.py`, `whatsapp_backfill.py`, `whatsapp_realtime.py`, migration 042, chat routes, `useWhatsAppChats.ts`) — converging it onto the organ is deferred until `monica` has run the organ in prod and the community product has adopted it (SW's richer behaviour — Julia pause, agente mirror, LGPD delete — needs named seams first).

## 5. Gaps / out-of-scope (with destinations)

| Item | Status | Destination |
|---|---|---|
| Twilio backend | not shipped | Provider-neutral surface is ready; add `integrations/whatsapp/twilio_client.py` + factory branch when a consumer needs it |
| Outbound media send (image/doc) | partial — `send_text` + `download_media` ship; rich outbound media is not in the Protocol | Additive Protocol extension; file when a consumer needs it |
| MCP-surfaced group tools (`waha.group.*`) | not shipped — `WahaClient`/`FakeWahaClient` ship the group surface, `mcp/waha` does not yet expose it | Slice W2 (deliberately deferred, wave0-design.md): `mcp/waha/tools/groups.py`, mirroring the existing `session`/`message`/`server` tool modules |
| Live confirmation of WAHA group-endpoint wire shapes | inferred from the WAHA Groups API's documented convention, not fetched from a live swagger this pass (no `waha` MCP / web access bound to this dispatch, live-VPS read denied) | Re-verify against `GET /api/server/version` + the live swagger (`waha.server.version` MCP tool, or `/api` on a bound session) before group ops carry real traffic; see `NOC-REMEDIATE[waha-verify]` in `mappers.py` |
| `devlikeapro/waha:latest` unpinned in `deploy/` | pre-existing, untouched by this slice (group endpoints differ by engine: WEBJS/NOWEB/GOWS — fleet runs NOWEB) | `deploy/services/compose.services.yml:106` / `deploy/fleet/compose.infra.prod.yml:109` — pin when a devops slice is scheduled |
| Read-state INBOUND (phone → app) | **not expressible with this transport** | `message.ack` carries acks only for messages WE sent; `chats/overview`'s `ChatSummary` (`{id,name,picture,lastMessage,_chat}`) has no top-level `unreadCount`. `sendSeen` therefore syncs read state OUT to the device, but reading a chat ON the phone does not clear the app's badge. Probe the untyped `_chat.unreadCount` once a session is `WORKING` if this needs revisiting. |
| Realtime delivery to the browser | shipped, but **not in this package** (the inbox organ §4d wires it) | `noctusai_lib.realtime` (SSE + Redis Streams) → `CONTEXT/PATTERNS/common/realtime-sse-bus.md` |
| Chatbot orchestration (buffer/worker/LLM dispatch) | **separate by design** | `noctusai_lib.domain.chatbot` + recipe `CONTEXT/PATTERNS/backend/whatsapp-chatbot-seed.md` |
| FB Pages / Instagram Graph | **separate package** | `noctusai_lib.integrations.meta` — `CONTEXT/INTEGRATIONS/meta.md` |

## 6. One WAHA per number (WAHA Core, 2026-10)

**Model.** WAHA CORE allows exactly one session (`default`) per container, so N numbers = N containers. Each is a declared instance in `deploy/fleet/waha-instances.yml`; `deploy/fleet/compose.waha.yml` is RENDERED from it (`noctus.dev.waha_instance action='render' write=True`) and `check_waha_instances_render_sync` (pre-commit, high) fails on drift -- never hand-copy a block. Each instance: service `waha-<name>`, container `noctus-waha-<name>`, own volume `noctus-waha-<name>` (sessions + NOWEB store), own `WAHA_<NAME>_API_KEY` / `_HMAC_SECRET` / `_DASHBOARD_PASSWORD` in `.env.fleet` (generated ON the VPS, `openssl rand -hex 32`; values never committed or transcribed), internal-only (`expose: 3000`, no published port; products call `http://waha-<name>:3000` over `noctus-net`), NOWEB store + fullSync on, `WHATSAPP_START_SESSION=default`, `/ping` healthcheck, `mem_limit`, `restart: unless-stopped`, image pinned (the shared `:latest` stays untouched).

**Capacity math.** Measured: ~208 MB RSS for the shared instance (NOWEB, one session). Budget 512 MB cap per instance (heap 384 MB; the store grows with history). VPS = 8 GB, 2 vCPU, 2 GB swap, fleet already resident: plan on roughly 10-15 instances before RAM binds, fewer if chat history is large; CPU spikes only during QR pairing / full sync. Re-measure with `waha_instance action='list'` (RSS column) before adding a batch; a million numbers is a multi-host problem (shard instances across hosts, same data file per host), not a bigger single VPS.

**Limits.** CORE = one session per container, no multi-device sessions; each number needs its own QR pairing and upkeep (re-pair when WhatsApp logs it out; a banned number is lost with its history). Dashboard/Swagger are reachable only through a tunnel route you add deliberately. WAHA Plus wins when you need many sessions in ONE container (it lifts the single-session limit) or engines/features beyond CORE -- a paid license, so switch only when per-container overhead (RAM + upkeep) outweighs it.

**Product contract.** `<PRODUCT>_WAHA_BASE_URL=http://waha-<name>:3000`, `<PRODUCT>_WAHA_SESSION=default`, and the product's webhook HMAC secret equal to that instance's `WAHA_<NAME>_HMAC_SECRET` (monica: `MONICA_WAHA_*`).

**Runbook.** (1) add the instance to `waha-instances.yml`, `render write=True`, add the 3 key names to `deploy/fleet/env.fleet.keys`; (2) `waha_instance action='plan' name=<n>` prints the key names + generate command; generate on the VPS; (3) `action='apply' confirm=True` (one instance at a time; refuses if keys are empty); (4) pair the QR via the product; (5) `action='list'` for health/RSS/session. Remove: `action='remove'` snapshots the volume, refuses a WORKING session without `force`, never deletes the volume.

