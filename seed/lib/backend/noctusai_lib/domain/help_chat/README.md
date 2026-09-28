# Help chat — the AI specialist bubble organ

A reusable **seed organ**: a floating chat bubble, present on every
authenticated page of a product, where the signed-in user talks to an AI
specialist that knows *that product* — its screens, mechanisms, rules — from
a single knowledge markdown file the product owns. Any product enables it
with one router-mount call plus a knowledge file. No product-specific
backend code required beyond that.

This directory (`noctusai_lib.domain.help_chat`) is the **backend** half.
The frontend organ is `HelpChatBubble` in
`seed/lib/frontend/src/components/help-chat/` (`@noctusai/lib`).

## Why "knowledge-only" (no customer-data access)

The assistant answers from the knowledge file ONLY — it never sees the
org's customers, deals, documents, or any other tenant data. This is a
deliberate, hard boundary: the backend never joins the LLM call to any
product table. It exists to explain the *product*, not to look things up
*in* the product. That keeps the LGPD story simple (no personal data ever
reaches the prompt) and makes the knowledge file the single place a product
maintains "what the assistant knows."

## Quick start (backend)

```python
# products/<slug>/backend/app/main.py (or a routers/help_chat_router.py)
from pathlib import Path

from noctusai_lib.domain.help_chat import create_help_chat_router

from app.dependencies import coerce_org_uuid, get_current_user_org

help_chat_router = create_help_chat_router(
    product_name="IgIg",
    knowledge_path=Path(__file__).parent / "help_chat_knowledge.md",
    auth_dependency=get_current_user_org,
    org_id_from_auth=lambda auth: str(coerce_org_uuid(auth[2])),
)
app.include_router(help_chat_router)
```

Mounts `POST /api/ajuda/chat` (the default `prefix="/api/ajuda"`).

**The knowledge file is loaded ONCE, right here, at router-construction
time** — which for a product means at process startup (routers are built
at import/startup time). A missing or empty knowledge file raises
`HelpChatKnowledgeMissing` and **fails app startup** — by design. A help
chat that starts with zero knowledge would confidently invent answers,
which is worse than the feature being absent (CLAUDE.md §1 "no silent
errors" / "no confident zero").

### Env var

The Anthropic key is resolved through the seed's normal credential chain —
`ANTHROPIC_API_KEY` in the product's `.env` (or an `org_settings` /
`platform_settings` override; see `noctusai_lib.config.credentials.
resolve_credential`). No help-chat-specific env var exists. Without a key
configured, every request answers `503 {"code": "ia_nao_configurada"}`
instead of 500ing.

## The knowledge file

Plain markdown, any structure. The behavioural system prompt (built-in,
pt-BR) is prepended automatically; your file is appended verbatim as
`--- Base de conhecimento do {product_name} ---`. Write it the way you'd
brief a new support hire: screen names, button labels, business rules,
known limitations. The model is instructed to say "not covered, contact
support" rather than invent anything not in this file — so the file's
completeness IS the assistant's ceiling.

## Request / response contract

```
POST {prefix}/chat            (default prefix: /api/ajuda)
Authorization: <whatever auth_dependency requires>
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "Como eu crio um negócio?"}
  ],
  "pagina_atual": "/comercial/negocios"   // optional — current route pathname
}
```

Response: `text/event-stream`. Every event is a single `data:` JSON line —
no custom `event:` types:

```
data: {"delta": "Para criar um "}

data: {"delta": "negócio, clique em..."}

data: {"done": true}
```

or, if the seam fails **mid-stream** (the one failure shape that cannot
become an HTTP status once bytes are already flowing):

```
data: {"error": {"code": "ia_indisponivel", "message": "O provedor de IA não respondeu. Tente novamente em instantes."}}
```

### Error mapping

| When | HTTP status | `code` |
|---|---|---|
| No Anthropic key configured | 503 | `ia_nao_configurada` |
| Org's monthly LLM budget exhausted | 429 | `orcamento_ia_excedido` |
| Per-user rate limit exceeded (default 20/min) | 429 | `limite_de_mensagens` |
| Anthropic API error / timeout | 502 | `ia_indisponivel` |
| Request body fails validation (unknown field, empty `messages`, non-`user` last message, too many turns, message too long) | 422 | validation-specific code |
| Missing/invalid auth | 401 | — |

A failure **before** the first streamed chunk answers as a real HTTP status
(the table above). A failure **after** streaming has started degrades to
an in-band SSE `error` event with the same `code`/`message` shape — the
frontend organ treats either shape as "show this error, offer retry."

## Configuration knobs

All keyword-only on `create_help_chat_router(...)`:

| Param | Default | What |
|---|---|---|
| `product_name` | — (required) | Used in the behavioural preamble. |
| `knowledge_path` | — (required) | `Path` to a markdown file, or a zero-arg `Callable[[], str]`. |
| `auth_dependency` | — (required) | The product's FastAPI auth dependency — same seam as `card_hub_routers`. |
| `org_id_from_auth` | — (required) | `(auth_value) -> org_id`. |
| `user_id_from_auth` | `org_id_from_auth` | `(auth_value) -> user_id`, keys the rate limit. Omit for per-org limiting. |
| `model` | `"claude-haiku-4-5"` | Cheap/fast, conversation-optimized. Override for a more demanding assistant. |
| `provider` | `"anthropic"` | Passed straight to the seed LLM stack. |
| `max_turns` | `20` | Max messages accepted per request (422 above). |
| `max_chars_per_message` | `4000` | Per-message length cap (422 above). |
| `rate_limit` | `20` | Requests/minute per user (429 above, `limite_de_mensagens`). |
| `prefix` | `"/api/ajuda"` | Router prefix. |

## What this organ does NOT do

- **Never persists conversation content server-side** — no table, no row,
  nothing written. The frontend organ is the only place a transcript
  lives (its own `sessionStorage`, capped, cleared per browser tab).
- **Never logs message text** — only sizes/latency/usage (`chunk_count`,
  `char_count`, `latency_ms`). A log line never contains what a user asked
  or what the assistant answered.
- **Never accesses customer/tenant data** — only the knowledge file + the
  conversation itself reach the prompt.
- **No non-streaming fallback** — the seed's `chat_completion_stream` seam
  streams for every registered provider (confirmed for `anthropic`, the
  default), so the "if streaming isn't available" branch the brief asked
  us to consider never triggers today. If a future provider genuinely
  cannot stream, `stream_fn` (a router-factory parameter) is the seam to
  swap for a `chat_completion`-backed non-streaming implementation without
  touching the router's request/response contract.

## Known seed gap: Anthropic prompt caching is requested but not yet wired end-to-end

This organ calls `noctusai_lib.integrations.llm.build_cached_messages(...,
provider="anthropic")`, which marks the system message
`"cache_control": {"type": "ephemeral"}` — the sanctioned seed idiom (see
`products/igig/backend/app/services/assistente.py` for the same call
shape). **However**, `AnthropicProvider._split_system_and_messages` (the
helper both `chat_completion` and `chat_completion_stream` use to build the
Anthropic SDK call) currently extracts only the system message's `content`
string and drops the `cache_control` key entirely — so today, no Anthropic
provider consumer actually gets prompt-cache pricing/latency benefits, this
organ included. This is a pre-existing seed gap, not something introduced
here; flagged as `scoped-improvement:` in this organ's delivery note for
the tech-lead to schedule as its own slice (touches a shared,
heavily-consumed provider file — outside a single-organ's blast radius).
