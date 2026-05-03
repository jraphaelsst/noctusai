# WhatsApp connector + chatbot framework (seed-lib)

> Two paired seed capabilities lifted from
> `whatsapp-google-scheduling/` 2026-05-03 via
> `projects/whatsapp-seed-absorption/`. Both opt-in per product.
>
> - **`noctusai_lib.integrations.whatsapp`** — WAHA-backed inbound parser
>   + outbound sender + signed-webhook FastAPI router factory.
> - **`noctusai_lib.domain.conversation`** — Redis-backed conversation
>   buffer + debounce + worker shell + OpenAI tool-loop dispatcher +
>   optional structured-output summary helper.
>
> Calendar + Maps adapters land in
> `noctusai_lib.integrations.{google_calendar,google_maps}`.

---

## 1. When to use

A product needs the **whatsapp** connector when:

- Inbound WhatsApp messages need to be received (via WAHA today;
  Twilio / Meta Cloud API parsers slot in later under the same
  `WhatsAppInboundMessage` shape).
- Outbound replies need to be sent through WAHA's `/api/sendText`.

A product needs the **chatbot framework** when:

- Inbound messages should buffer + debounce so multi-message bursts
  aggregate into one LLM turn.
- A worker should poll for "due" conversations and dispatch the LLM.
- The LLM uses tool-calling and the bot owns its own tool registry.
- Optional: idle conversations should be summarized via OpenAI
  structured output.

The two are independent. A product may wire WhatsApp transport with a
non-LLM dispatcher (campaign reply); another may wire the chatbot
framework on a different channel (Telegram, in-app messaging) by
swapping the connector.

---

## 2. Public surface

### Connector — `noctusai_lib.integrations.whatsapp`

| Symbol | Role |
|---|---|
| `WhatsAppInboundMessage`, `WhatsAppMedia` | Provider-neutral inbound shape (legacy `Waha*` aliases preserved). |
| `WhatsAppPayloadError`, `WhatsAppIgnoredEvent` | Parser-side errors (validation vs intentional ignore). |
| `parse_waha_inbound_message(payload)` | WAHA-specific parser. Other providers add sibling parsers under the same return shape. |
| `chat_id_for_phone(phone)`, `phone_from_chat_id(chat_id)` | WAHA chat-id ↔ E.164 conversions. |
| `WahaClient(base_url, api_key, session)` | sync + async `send_text` + `download_media`. |
| `WhatsAppSettings` | Pydantic config (`base_url`, `api_key`, `session`, `webhook_hmac_secret`). |
| `create_whatsapp_webhook_router(settings, on_message)` | FastAPI APIRouter factory. Verifies HMAC-SHA256 hex signatures (when `webhook_hmac_secret` is set), dedupes by `provider_message_id`, dispatches to `on_message(inbound)`. |

### Framework — `noctusai_lib.domain.conversation`

| Symbol | Role |
|---|---|
| `ConversationBufferService(redis_client, ...)` | Redis list-per-conversation memory + ZSET debounce + ZSET idle queue + XADD audit stream. |
| `QueuedConversationMessage` | Buffer message dataclass. |
| `RedisBufferClient` Protocol | The Redis surface the buffer needs (`redis.Redis` satisfies it; tests use a fake). |
| `ConversationWorker(buffer_service, processor, idle_processor=None, ...)` | Poll loop + due/idle dispatch. Stop via `worker.stop()` (signal-handler compatible). |
| `LLMDispatcher(client, model, max_tool_iterations=5)` | OpenAI chat-completion + tool-loop runner. Returns final text reply or fallback on iteration exhaustion. |
| `ToolCall`, `ToolResult` | Normalized dispatcher I/O. |
| `ToolHandler`, `AuditWriter` | Consumer-supplied callables (audit_writer optional; default no-op). |
| `memory_to_chat_messages`, `format_conversation_for_transcript` | Pure-function translators. |
| `image_bytes_to_data_url`, `audio_bytes_to_named_buffer` | OpenAI vision + audio helpers. |
| `summarize_conversation(client, model, memory, output_schema, system_prompt, ...)` | Structured-output summary runner (opt-in). |

### Settings (consumer-side)

```python
# In your product's BaseAppSettings subclass:
class Settings(BaseAppSettings):
    waha_base_url: str = ""
    waha_api_key: str | None = None
    waha_session: str = "default"
    waha_webhook_hmac_secret: str | None = None

    conversation_memory_ttl_seconds: int = 3600
    message_debounce_seconds: int = 8
    conversation_idle_timeout_seconds: int = 1800
    redis_stream_maxlen: int = 10_000
    worker_poll_seconds: float = 2.0
    worker_due_batch_size: int = 25

    openai_model: str = "gpt-4o-mini"  # already in noctusai_lib.integrations.llm scope
```

`redis_url` lives on the `BaseAppSettings` base already.

---

## 3. Wiring recipe (consumer side)

### Step 1: build the WhatsApp settings + connector router

```python
from fastapi import APIRouter
from noctusai_lib.integrations.whatsapp import (
    WhatsAppSettings, create_whatsapp_webhook_router, WhatsAppInboundMessage,
)
from noctusai_lib.integrations.redis import make_redis_client
from noctusai_lib.domain.conversation import (
    ConversationBufferService, QueuedConversationMessage,
)

whatsapp_settings = WhatsAppSettings(
    base_url=settings.waha_base_url,
    api_key=settings.waha_api_key,
    session=settings.waha_session,
    webhook_hmac_secret=settings.waha_webhook_hmac_secret,
)

redis = make_redis_client(settings.redis_url)

buffer = ConversationBufferService(
    redis,
    memory_ttl_seconds=settings.conversation_memory_ttl_seconds,
    debounce_seconds=settings.message_debounce_seconds,
    idle_timeout_seconds=settings.conversation_idle_timeout_seconds,
    stream_maxlen=settings.redis_stream_maxlen,
)


async def handle_inbound(inbound: WhatsAppInboundMessage) -> None:
    buffer.buffer_inbound(
        QueuedConversationMessage(
            conversation_id=inbound.from_phone,
            text=inbound.text,
            direction="inbound",
            provider_message_id=inbound.provider_message_id,
        )
    )


router = create_whatsapp_webhook_router(whatsapp_settings, handle_inbound)
```

Mount via `app.include_router(router, prefix="/webhooks/whatsapp")`
or via `standard_routers=[..., "whatsapp_webhook"]` once the seed factory
adopts named routers.

### Step 2: build the worker

```python
from noctusai_lib.domain.conversation import (
    ConversationWorker, LLMDispatcher, memory_to_chat_messages,
    ToolCall, ToolResult,
)
from noctusai_lib.integrations.whatsapp import WahaClient

waha = WahaClient(
    base_url=settings.waha_base_url,
    api_key=settings.waha_api_key,
    session=settings.waha_session,
)

dispatcher = LLMDispatcher(
    client=openai_client,
    model=settings.openai_model,
    max_tool_iterations=5,
)

PRODUCT_SYSTEM_PROMPT = """..."""  # product-specific prose
PRODUCT_TOOLS = [...]               # OpenAI tools_payload list[dict]


def my_tool_handler(call: ToolCall) -> ToolResult:
    # Look up the tool by name, run it, return ToolResult.
    ...


def processor(conversation_id: str, memory: list[dict]) -> None:
    messages = [
        {"role": "system", "content": PRODUCT_SYSTEM_PROMPT},
        *memory_to_chat_messages(memory),
    ]
    reply = dispatcher.reply(
        messages=messages,
        tools=PRODUCT_TOOLS,
        tool_handler=my_tool_handler,
        # audit_writer=make_audit_writer(...),  # optional, see KB § PATTERNS/llm-tool-audit.md
    )
    if reply:
        waha.send_text_sync(chat_id_for_phone(conversation_id), reply)
        buffer.append_to_memory(QueuedConversationMessage(
            conversation_id=conversation_id, text=reply, direction="outbound",
        ))


worker = ConversationWorker(
    buffer_service=buffer,
    processor=processor,
    poll_seconds=settings.worker_poll_seconds,
    due_batch_size=settings.worker_due_batch_size,
)
# In your worker process's main():
import signal
signal.signal(signal.SIGTERM, worker.stop)
signal.signal(signal.SIGINT, worker.stop)
worker.run_forever()
```

### Step 3 (optional): idle summary

```python
from pydantic import BaseModel
from noctusai_lib.domain.conversation import summarize_conversation


class MySummary(BaseModel):
    intent: str
    next_step: str | None


def idle_processor(conversation_id: str, memory: list[dict]) -> None:
    summary = summarize_conversation(
        client=openai_client,
        model=settings.openai_model,
        memory=memory,
        output_schema=MySummary,
        system_prompt=MY_SUMMARY_SYSTEM_PROMPT,
    )
    # persist `summary` somewhere


worker.idle_processor = idle_processor  # opt-in; default off
```

---

## 4. What stays consumer-side

- **System prompts.** Always product-specific (sibling was pt-BR
  real-estate; therapy is a different domain entirely). Per
  project §7 Q3 the seed never ships SYSTEM_PROMPT constants.
- **Tool registry + tool handler.** The dispatcher takes OpenAI
  `tools_payload` directly + a handler callable. Each product owns
  what tools its bot can call.
- **Audit-row persistence.** `LLMDispatcher.reply(audit_writer=...)`
  is the seam to `noctusai_lib.domain.ai.tool_audit` (see
  `KB § PATTERNS/llm-tool-audit.md`). Default is no-op so the
  dispatcher works without audit wiring.
- **User-context resolution.** Phone → user lookup (with LID-aware
  resolution if needed) is product-specific.
- **Outbound chat-id resolution.** WAHA's `chat_id` may differ from
  reconstructed-from-phone (`@lid_*` chats). Consumer reads it from
  inbound metadata and passes through.

---

## 5. Documented behavior to know about

### Debounce race (preserved from sibling)

`due_conversations(now)` returns IDs whose due timestamp ≤ now. The
worker reads the conversation memory + claims (`zrem`), but a NEW
inbound between the read and the claim could push the due timestamp
forward — the worker may then dispatch on slightly stale memory.
Sibling accepted this. We preserve the behavior; project §7 Q5 leaves
a follow-up slot open (`projects/conversation-buffer-race-fix/`).

### Idle-processor exception swallowing

`sweep_idle_once` catches exceptions from `idle_processor`, logs them,
and **does NOT clear the conversation** so the next sweep retries.
This matches sibling. The successful `processor` path (due) DOES claim
even on processor exception (caller's responsibility to handle errors
inside `processor`).

### In-process webhook dedup

`create_whatsapp_webhook_router` keeps an in-process `seen_ids` set
for `provider_message_id` dedup. This is **best-effort within a
process**; a worker restart resets the set. For cross-process / cross-
restart dedup, the consumer should add a Redis-backed dedup layer
inside `on_message` (or use the buffer's `provider_message_id` field
to dedup at insert time). Sibling did the latter via DB unique index;
that pattern stays consumer-side.

---

## 6. What's NOT in the seed (deferred / consumer-side / out-of-scope)

- `GoogleCalendarAdapter` (service-account) + `GoogleCalendarOAuthAdapter`
  (consenting-user) — deferred to a follow-up project. The seed ships
  `FakeCalendarAdapter` + types + mappers; the real adapters need
  `googleapiclient`/`google-auth` runtime deps + a credential-repo
  abstraction story. See `KB § INTEGRATIONS/google-calendar-real-adapters.md`
  (forthcoming) when the follow-up lands.
- Phone normalization beyond `chat_id_for_phone` / `phone_from_chat_id`
  (LID-aware auth, etc.) — product-specific resolver.
- Conversation-summary BI schema + retention policy.
- Multi-tenant Redis isolation — Redis URL is per-product today.
- Localization (per project §7 Q6, deferred to
  `projects/conversation-i18n/` once a second-language consumer surfaces).

---

## 7. Tests + verification

- `seed/lib/backend/tests/integrations/whatsapp/` — 21 cases (mappers + router).
- `seed/lib/backend/tests/domain/conversation/` — 28 cases (buffer +
  worker + dispatcher + mappers + summary).
- `seed/lib/backend/tests/integrations/google_calendar/` — 9 cases
  (Fake adapter + mappers).
- `seed/lib/backend/tests/integrations/google_maps/` — 11 cases (Static
  + mocked Google Maps + mappers).

Run: `cd seed/lib/backend && pytest tests/{integrations,domain/conversation}/`.

---

## 8. Related

- `KB § PATTERNS/seed-lib-layout.md` — placement rationale (`integrations/`
  for transports + adapters; `domain/conversation/` for the framework).
- `KB § PATTERNS/webhook-signatures.md` — `verify_hmac_sha256_hex` is the
  helper the WhatsApp router uses.
- `KB § PATTERNS/llm-tool-audit.md` — audit_writer wiring for the
  dispatcher.
- `KB § PATTERNS/llm-bot-security.md` — defense trio for the LLM
  surface (sanitize / arg-validate / rate-limit).
- `KB § PATTERNS/scheduling-seed.md` — pairs naturally with the chatbot
  framework when the bot proposes appointment slots.
- `projects/whatsapp-seed-absorption/PROJECT.md` — origin project (will
  be deleted at close; see git history for the original).
- Future: first-consumer wiring at
  `projects/imobi-scheduling-bot-creation/` (real-estate scheduling bot
  on top of this seed).
