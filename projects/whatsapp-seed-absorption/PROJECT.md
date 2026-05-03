# whatsapp-seed-absorption — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update §11. See `CLAUDE.md → Engineering Philosophy → Projects are living`.
>
> **Write for a zero-context reader.** Inline context in §1, quote the user in §2, name files with paths in §5, pair every §7 Open Question with an evidence-backed recommendation, make §10 commands copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Design captured → Phase 0 ready (audit before any code lands)
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `projects/mcp-server-expansion/PROJECT.md` (sibling effort — absorbs the WhatsApp bot's MCP toolkit), `projects/llm-tool-call-audit/PROJECT.md` (sibling effort — absorbs the bot's tool-call audit pattern), `KB § 04-SHARED-LIBRARY.md` (target lib catalog), `KB § PATTERNS/seed-lib-layout.md` (6-layer rule for placement decisions).
- **Project slug:** `whatsapp-seed-absorption` — cross-product / seed concern (touches `noctusai_lib`, methodology KB, multiple future product consumers). Lives at `projects/<slug>/` per `KB § PATTERNS/project-execution.md §1`.

---

## 1. Context & Purpose

Sibling repo at `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/` runs a tested, working WhatsApp scheduling bot for real-estate content production. The user has validated it as a working MVP. The build covers WAHA webhook ingest → Redis-backed conversation buffer + debounce → worker that processes "due" conversations → OpenAI structured-output / tool-loop chat → Google Calendar adapter (OAuth + service-account + Fake fallback) → Google Maps routing (with static fallback) → WAHA outbound replies. End-to-end, with audit trail and idempotency.

Today none of our products has a WhatsApp surface. As soon as one does (therapy patient communication, daily-life check-ins, ERP agent coordination, mailing campaign-reply handling), each would have to re-solve the same problems: signature verification, conversation memory, debounce, tool-loop dispatch, calendar/maps integrations. That's the textbook recurrence-rule trigger before the recurrence even fires.

This project lifts the entire validated stack into `noctusai_lib` as a **seed feature** — two import-able capabilities any product can opt into:

1. **WhatsApp connector** — WAHA-backed inbound parser + outbound sender + signature verification. Vendor-neutral by design (`noctusai.whatsapp.send_text` style; swapping to Twilio / Cloud API later does not rename the seam).
2. **Chatbot framework** — conversation buffer + debounce + worker shell + OpenAI tool-loop dispatch. Channel-agnostic (a product could compose it with a different connector). Tools, system prompts, and intent registries are product-supplied.

Both are proven; the work is portability + adaptation, not redesign.

---

## 2. Confirmed constraints

Decisions the user made in the 2026-05-03 absorption-evaluation session. Direct quotes preserved where decisive.

- **Bring everything, no skips** — *"We're gonna bring it all, no skips, it's already a tested working mvp, we will only make the portability of it to our repo and adapt it to our codebase."* — Replication of the entire vertical slice (connector + framework + adapters + audit + tests) is the goal. Scope reductions only happen if a piece is genuinely identical to existing `noctusai_lib` (e.g., webhook HMAC verifier already exists; the bot re-implemented it locally and we adopt the existing one). *(Prevents "absorb the easy half, defer the rest" drift.)*
- **Seed feature, opt-in per product** — *"We'll keep it as a seed feature that every product can import inside their own scope."* — Lives in `seed/backend/lib/noctusai_lib/`. No product is forced to wire it. *(Drives §3a opt-in litmus.)*
- **Two distinct features inside one project** — *"the whatsapp connection is gonna be a feature, as well as the conversation buffer. They are proven whatsapp wired workflows to conversations with ais. Both proven, we can create chatbots from scratch to whatever we want, and we also have the whatsapp connector."* — Connector and framework are separable; products can wire one without the other (e.g., a product using a different chat channel still gets the framework; a product wanting WAHA-only outbound notifications gets the connector without the framework). *(Drives the two-namespace split in §5.)*
- **Validated MVP — port the shape** — *"the exact way it is right now as it's validated"* — preserve the bot's API shape (Redis key names, debounce semantics, audit-row schema) so the upstream tests transfer cleanly. Refactors are deferred to follow-up projects unless a refactor is required by the lift itself. *(Prevents bikeshedding the absorption.)*
- **Massive work — track in this file** — *"as it's gonna be a massive work. The idea is to bring everything"* — this PROJECT.md is the single source of truth for the lift; every file moved / adapted gets a row in §5's there→here map and a checkbox in §6.

---

## 3. Design principles

How we're approaching this specific lift (beyond the platform-wide `CLAUDE.md` rules).

1. **Preserve the validated shape.** Redis key names, debounce defaults, audit-row schema, system-prompt structure all carry over verbatim unless adaptation is forced by the noctusai_lib placement. *Why:* the bot's correctness is empirically established; gratuitous renames invalidate the validation.
2. **Two namespaces, two seams.** WhatsApp connector and chatbot framework are physically separated inside `noctusai_lib` so a product can wire either without the other. *Why:* the bot bundles them only because it has one concrete use case; we'd be locking in that bundling if we shipped one combined seam.
3. **Adapter dual-path with Fake fallback is a convention, not a feature.** Calendar / routing / WhatsApp connector each follow OAuth-or-service-account-or-Fake fallback (`app/services/calendar/__init__.py:34-59`). We codify this as a `noctusai_lib.integrations` convention while doing the lift — first time documented in the platform.
4. **First-consumer wiring lives in a follow-up project.** This project lands the lib + reference tests + KB doc. Wiring (e.g., therapy-whatsapp-pilot) is its own project so the absorption isn't contaminated by product-specific decisions. *Exception:* if no product wires it within ~2 weeks of landing, that's a smell — we revisit whether the abstraction is right.
5. **Two adjacent projects do part of the work.** `mcp-server-expansion` absorbs the bot's `mcp_server/` tools (Calendar, Maps, OpenAI audio/vision, scheduling, WhatsApp send-text). `llm-tool-call-audit` absorbs the bot's `ToolCallAudit` model + dispatch wrapper into `noctusai_lib.domain.ai`. This project explicitly **does not** duplicate either; it depends on both for end-to-end completeness.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Run the six-question checklist (`KB § GUIDES/seed-first-design.md`):

1. **Is the contract identical for every product?** YES. The two seams (`WhatsAppConnector`, `ChatbotFramework`) are platform capabilities; their contract is the same regardless of product.
2. **Is the data source product-specific?** YES per consumer (each product owns its `users` + tool registry + intents + system prompt). Container is seedable; the per-product wiring is the data injection at boot.
3. **Is the placement product-specific?** NO for the lib (`seed/backend/lib/noctusai_lib/`). YES for the wiring — each product imports and configures inside its own `app/services/`.
4. **Is the visibility / permission rule the same?** YES — uniform gate. Each consumer enforces its own authorization at the inbound boundary; the framework only provides the seam.
5. **Does the seam already exist in seed?** NO — both `noctusai_lib.integrations.whatsapp` and `noctusai_lib.domain.conversation` are new namespaces. `noctusai_lib.security.webhook_signatures` already exists and is reused (no re-implementation).
6. **Default-on or opt-in?** OPT-IN — sometimes-applicable. Most products will not wire WhatsApp; the framework is dormant unless `configure_whatsapp_module(...)` and `configure_chatbot_module(...)` are called from the product's `create_product_app(...)` factory call.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — product-specific data wiring around seed-shaped containers (intent registry + system prompt + tool registry per product, plus `configure_*_module(...)` calls in the product's factory). Acceptable for product-specific data sources.

**Phase plan implications:** §6 phases all work in `seed/backend/lib/noctusai_lib/` and `KB`. **No phase walks through products.** First-product wiring is a follow-up project (e.g., `products/therapy-platform/projects/therapy-whatsapp-pilot/`). Per the language-time replication-to-seed rule, no phase here uses "per-product X" framing.

---

## 4. Scope

**In scope:**

- WhatsApp connector module: `noctusai_lib/integrations/whatsapp/` (WAHA client, inbound parser, outbound sender, media downloader, idempotency hook).
- Chatbot framework module: `noctusai_lib/domain/conversation/` (Redis-backed buffer + debounce, worker shell, OpenAI tool-loop dispatcher, conversation summary service).
- Calendar adapter promotion: `noctusai_lib/integrations/google_calendar/` (OAuth + service-account + Fake fallback).
- Routing adapter promotion: `noctusai_lib/integrations/google_maps/` (Routes/Distance Matrix + Static fallback).
- Webhook signature reuse: bot's local `app/security/webhook_hmac.py` discarded; consumers use existing `noctusai_lib.security.webhook_signatures`.
- Adapter-dual-path-with-Fake-fallback convention documented at `KB § PATTERNS/integrations-fake-fallback.md`.
- Reference tests transferred from `whatsapp-google-scheduling/tests/` into `seed/backend/lib/tests/` (preserving the validation evidence).
- KB pattern doc: `KB § PATTERNS/whatsapp-chatbot-seed.md` covering wiring recipe, configuration knobs, opt-in surface.

**Out of scope (for now — with reason):**

- First-product wiring — its own follow-up project so the absorption isn't contaminated by product-specific decisions.
- `ToolCallAudit` model + dispatch wrapper — owned by `projects/llm-tool-call-audit/PROJECT.md`. This project depends on its completion for end-to-end completeness but does not duplicate it.
- MCP tool surface (Calendar / Maps / OpenAI audio/vision / scheduling / whatsapp send-text) — owned by `projects/mcp-server-expansion/PROJECT.md`. The bot's `mcp_server/tools/` get absorbed into our MCP, not into `noctusai_lib`.
- Multi-channel abstraction (Twilio, Cloud API alternatives) — `noctusai.whatsapp.*` namespacing is provider-neutral by design but only WAHA is implemented in this project. Adding alternative providers is a follow-up project once a second consumer requires it.
- Race-condition fix in the debounce ZSET (sibling has a documented race when message #2 arrives after message #1 is claimed) — preserve the bot's behavior verbatim; fix is a follow-up project so this absorption stays a portability operation, not a redesign.

---

## 5. Architecture / Data Model

### 5.1 The there → here map

Sibling source paths on the left, target placement in `noctusai/` on the right. Every row is a checklist item driven by a phase in §6.

#### WhatsApp connector

| There (`whatsapp-google-scheduling/`) | Here (`noctusai/seed/backend/lib/noctusai_lib/`) | Notes |
|---|---|---|
| `app/services/waha_service.py` (WAHA inbound parser, `WahaInboundMessage` dataclass) | `integrations/whatsapp/inbound.py` | Provider-neutral parser interface; WAHA is the first implementation. |
| `app/api/webhooks.py` (HTTP webhook handler, idempotency, persistence) | `integrations/whatsapp/router.py` (FastAPI APIRouter factory: `create_whatsapp_webhook_router(...)`) | Mounted via `standard_routers=[..., "whatsapp_webhook"]` in `create_product_app(...)`. |
| `app/security/webhook_hmac.py` (HMAC SHA-256 verifier) | (DISCARD — use existing `noctusai_lib/security/webhook_signatures.py`) | The bot re-implemented what we already have. Consumers wire `verify_webhook_signature(secret, ...)` directly. |
| WAHA outbound POST helper (lives inside `app/workers/conversation_worker.py:_resolve_chat_id` + outbound dispatch) | `integrations/whatsapp/outbound.py` (`WahaOutboundClient` class) | Single responsibility: send text / media to WAHA. |
| Media-download flow (`webhooks.py:107-155` audio + image fetch) | `integrations/whatsapp/media.py` | Calls into `noctusai_lib/llm/audio.py` + `noctusai_lib/llm/vision.py` (those exist? — verify in Phase 0; if not, scope a sub-task to land them under `integrations/llm/`). |

#### Chatbot framework

| There | Here | Notes |
|---|---|---|
| `app/services/conversation_buffer_service.py` (Redis list buffer + ZSET debounce) | `domain/conversation/buffer.py` | TTL + max-message defaults preserved verbatim. Configuration via `configure_conversation_module(...)`. |
| `app/redis_client.py` (Redis connection helper) | (DISCARD if `noctusai_lib/integrations/redis.py` exists; otherwise create as `integrations/redis.py`) | Phase 0 verifies whether we already have a Redis client; if so, the framework imports from there. |
| `app/workers/conversation_worker.py` (poll loop, due dispatch, idle sweep) | `domain/conversation/worker.py` (`ConversationWorker` class with `run_forever()` + `process_due_once()` + `sweep_idle_once()`) | Worker is product-instantiable; product code defines the LLM dispatcher passed to the worker. |
| `app/services/openai/conversation.py` (`ConversationGptService.reply()` — system prompt + tool loop) | `domain/conversation/llm_dispatcher.py` | OpenAI tool-loop dispatcher; tools, system prompt, max iterations supplied per consumer. |
| `app/services/openai/tools/registry.py` (`ToolRegistry`, `dispatch()`, audit row writes) | (PARTIAL — registry shape lifts here; audit-row writes owned by `projects/llm-tool-call-audit/`) | This project lifts only the registry / dispatch shape. Audit persistence is `noctusai_lib/domain/ai/tool_audit.py` (sibling project). |
| `app/services/openai/mappers.py` (`memory_to_chat_messages` etc.) | `domain/conversation/mappers.py` | Pure-function translators. |
| `app/services/conversation_summary_service.py` (idle-time summarizer) | `domain/conversation/summary.py` | Optional; opt-in via configuration flag. |

#### Adapters (Calendar, Maps)

| There | Here | Notes |
|---|---|---|
| `app/services/calendar/__init__.py` (OAuth → service-account → Fake fallback) | `integrations/google_calendar/__init__.py` | Carries `FakeCalendarAdapter` + protocol. |
| `app/services/calendar/google_oauth.py` | `integrations/google_calendar/oauth.py` | OAuth credential persistence pattern; uses noctusai-side credential repo. |
| `app/services/calendar/google_service_account.py` | `integrations/google_calendar/service_account.py` | |
| `app/services/calendar/fake.py` | `integrations/google_calendar/fake.py` | |
| `app/services/routing/__init__.py` (Maps → Static fallback) | `integrations/google_maps/__init__.py` | |
| `app/services/routing/google_maps.py` | `integrations/google_maps/routes.py` | |
| `app/services/routing/static.py` | `integrations/google_maps/static.py` | |

#### Tests

| There | Here | Notes |
|---|---|---|
| `tests/test_conversation_buffer_service.py` | `seed/backend/lib/tests/conversation/test_buffer.py` | Verbatim port; verifies validated behavior. |
| `tests/test_conversation_worker.py` | `seed/backend/lib/tests/conversation/test_worker.py` | |
| `tests/test_scheduling_service.py` | (OWNED BY `projects/scheduling-engine-seed/`) | |
| `tests/test_calendar_adapters.py` | `seed/backend/lib/tests/integrations/test_google_calendar_adapters.py` | |
| `tests/test_routing_adapters.py` | `seed/backend/lib/tests/integrations/test_google_maps_adapters.py` | |
| `tests/test_waha_service.py` | `seed/backend/lib/tests/integrations/test_whatsapp_inbound.py` | |
| `tests/test_webhooks.py` | `seed/backend/lib/tests/integrations/test_whatsapp_router.py` | |
| `tests/test_openai_conversation.py` | `seed/backend/lib/tests/conversation/test_llm_dispatcher.py` | |

#### Configuration

| There (`app/config.py`) | Here | Notes |
|---|---|---|
| `WAHA_BASE_URL`, `WAHA_API_KEY`, `WAHA_SESSION`, `WAHA_WEBHOOK_HMAC_SECRET` | `noctusai_lib/integrations/whatsapp/settings.py::WhatsAppSettings` | Pulled by `configure_whatsapp_module(...)`. |
| `CONVERSATION_MEMORY_TTL_SECONDS`, `MESSAGE_DEBOUNCE_SECONDS`, `REDIS_STREAM_MAXLEN`, `WORKER_POLL_SECONDS`, `WORKER_DUE_BATCH_SIZE` | `noctusai_lib/domain/conversation/settings.py::ConversationSettings` | |
| `OPENAI_MODEL`, `OPENAI_API_KEY` | (USE EXISTING `noctusai_lib/llm/`) | Already in our LLM module. |

### 5.2 Wiring contract (what a consuming product looks like)

A product opts in by extending its `create_product_app(...)` call:

```python
# products/<product>/backend/app/main.py
from noctusai_lib.integrations.whatsapp import configure_whatsapp_module
from noctusai_lib.domain.conversation import configure_conversation_module, build_default_dispatcher

configure_whatsapp_module(settings=settings.whatsapp)
configure_conversation_module(
    settings=settings.conversation,
    dispatcher=build_default_dispatcher(
        system_prompt=THERAPY_SYSTEM_PROMPT,
        tools=therapy_tool_registry,
        max_tool_iterations=5,
    ),
)
app = create_product_app(
    standard_routers=[..., "whatsapp_webhook"],
    lifespan_extras=[start_conversation_worker],
    ...
)
```

The product owns the **system prompt**, **tool registry**, **authorization rule**, and **lifespan wiring**. The seed owns the **plumbing**.

### 5.3 What's NOT in this project (cross-references)

- `mcp_server/tools/google/calendar/*`, `mcp_server/tools/google/maps/*`, `mcp_server/tools/openai/*`, `mcp_server/tools/noctus/whatsapp/send_text.py` → owned by `projects/mcp-server-expansion/`.
- `mcp_server/tools/noctus/scheduling/suggest_slots.py` + `app/services/scheduling_service.py` → owned by `projects/scheduling-engine-seed/`.
- `app/services/openai/tools/registry.py` audit-row write side → owned by `projects/llm-tool-call-audit/`.

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge as work progresses.

### Phase 0 — Audit before any code lands

- [ ] Read every file listed in §5.1 in the sibling repo end-to-end (no skim).
- [ ] Confirm whether `noctusai_lib/integrations/redis.py` exists; if not, scope sub-task in Phase 1.
- [ ] Confirm whether `noctusai_lib/llm/audio.py` and `noctusai_lib/llm/vision.py` exist; if not, scope sub-tasks in Phase 1.
- [ ] Verify `noctusai_lib/security/webhook_signatures.py` covers the bot's HMAC shape (sibling re-implemented; we should be able to discard).
- [ ] Run `grep -rIn "conversation\|debounce\|whatsapp\|chatbot" seed/backend/lib/noctusai_lib/` to surface any partial overlap with existing seed lib code.
- [ ] Verify the bot's `tests/` actually pass against the sibling code today (the validation we're inheriting).
- [ ] If Phase 0 invalidates §6, **revise §6 in-place + log in §11** (per `KB § PATTERNS/project-execution.md § 2.5 Phase 0 audits`).

### Phase 1 — Foundation: namespace skeletons + settings

- [ ] Create `seed/backend/lib/noctusai_lib/integrations/whatsapp/` (`__init__.py`, `settings.py`, `client.py` stubs).
- [ ] Create `seed/backend/lib/noctusai_lib/domain/conversation/` (`__init__.py`, `settings.py`, stubs for `buffer.py` / `worker.py` / `llm_dispatcher.py` / `mappers.py` / `summary.py`).
- [ ] Create `seed/backend/lib/noctusai_lib/integrations/google_calendar/` and `google_maps/` skeletons.
- [ ] Backfill `noctusai_lib/integrations/redis.py` if Phase 0 found it missing.
- [ ] Run `bash scripts/verify-kb-sync.sh` (must pass before any further work).

### Phase 2 — WhatsApp connector lift

- [ ] Port `WahaInboundMessage` parser → `integrations/whatsapp/inbound.py` (preserve dataclass shape verbatim).
- [ ] Port outbound WAHA client → `integrations/whatsapp/outbound.py`.
- [ ] Port media-download flow → `integrations/whatsapp/media.py`.
- [ ] Build `create_whatsapp_webhook_router(...)` factory at `integrations/whatsapp/router.py`. Reuses `noctusai_lib/security/webhook_signatures.py`. Idempotency on `provider_message_id` preserved.
- [ ] Wire `configure_whatsapp_module(...)` (FastAPI dep factory pattern per `KB § PATTERNS/backend.md`).
- [ ] Port + run `tests/test_waha_service.py` and `tests/test_webhooks.py` against the new modules. Must pass.

### Phase 3 — Chatbot framework: buffer + debounce

- [ ] Port `conversation_buffer_service.py` → `domain/conversation/buffer.py`. Redis key names preserved (`conversation:memory:{id}`, `queue:conversation_due`, `queue:conversation_idle_due`, `queue:conversation_messages`). TTL + max-msg defaults preserved.
- [ ] Port + run `tests/test_conversation_buffer_service.py`. Must pass.
- [ ] Document the documented debounce race in code comment (preserve behavior verbatim per §2 constraint; fix deferred).

### Phase 4 — Chatbot framework: worker shell

- [ ] Port `conversation_worker.py:run_forever / process_due_once / sweep_idle_once` → `domain/conversation/worker.py`. Worker takes a `dispatcher` callable (DI), so product code supplies the LLM-tool-loop. No hardcoded OpenAI dependency.
- [ ] Port worker tests. Must pass.

### Phase 5 — Chatbot framework: LLM dispatcher

- [ ] Port `ConversationGptService.reply()` (tool-loop, max iterations) → `domain/conversation/llm_dispatcher.py`.
- [ ] Tool registry shape lands here (the dispatch logic). **Audit-row persistence side does NOT land here** — it's owned by `projects/llm-tool-call-audit/`. The dispatcher accepts an optional `audit_writer` callable (no-op default).
- [ ] Port `mappers.py` (pure functions).
- [ ] Port + run `tests/test_openai_conversation.py`. Must pass (mocking the OpenAI client and `audit_writer`).

### Phase 6 — Conversation summary (optional capability)

- [ ] Port `conversation_summary_service.py` → `domain/conversation/summary.py`.
- [ ] Wire idle-summary as opt-in via `ConversationSettings.enable_idle_summary` flag (default OFF).
- [ ] Tests.

### Phase 7 — Calendar adapter dual-path lift

- [ ] Port `app/services/calendar/__init__.py` factory + OAuth + service-account + Fake adapters → `integrations/google_calendar/`.
- [ ] Tests.
- [ ] Document the dual-path-with-Fake convention in `KB § PATTERNS/integrations-fake-fallback.md` (NEW pattern doc — first instance landing).
- [ ] Add `KB § INDEX.md` entry; add `CLAUDE.md §3 Map` pointer.
- [ ] **Calendar `requestId` idempotency** (folded from sibling `idempotency-keys` idea): adapter accepts an optional `request_id` parameter; consumers pass a deterministic ID derived from `appointment_request.id` so retries don't double-create events.
- [ ] **OAuth activation lessons surface in consumer products, not lib** (folded from sibling `google-oauth-activation` PROJECT — that project was mostly done over there; the lib lifts only the adapter, the runbook lives in `products/<consumer>/README.md` per `projects/imobi-scheduling-bot-creation/` Phase 6).

### Phase 8 — Maps routing adapter dual-path lift

- [ ] Port `app/services/routing/__init__.py` + adapters → `integrations/google_maps/`.
- [ ] Tests.

### Phase 9 — KB pattern doc + INDEX

- [ ] Write `KB § PATTERNS/whatsapp-chatbot-seed.md` covering: when to wire, settings inventory, system-prompt + tool-registry contracts, opt-in surface, debounce semantics (with the documented race), audit-row dependency on `noctusai_lib.domain.ai`.
- [ ] Update `KB § INDEX.md`.
- [ ] Update `CLAUDE.md §3 Map` with two pointers (one for the connector, one for the framework).
- [ ] Update `KB § 04-SHARED-LIBRARY.md` catalog with the new namespaces.

### Phase 10 — Final verification + handoff

- [ ] `cd seed/backend/lib && pytest` — full lib suite green.
- [ ] `bash scripts/verify-kb-sync.sh` — green.
- [ ] `python mcp/noctusai/cli.py --review` — keeper observation only; triage findings 3-way (formalize / refactor / accept-with-rationale).
- [ ] Three-way sync (KB ↔ CLAUDE.md ↔ memory) verified.
- [ ] Scaffold the first-consumer follow-up project (NOT the implementation) at `products/<product>/projects/<product>-whatsapp-pilot/` so this project's deliverable has a downstream landing pad. The follow-up's choice of product (therapy / daily-life / mailing) is an open question — see §7.

---

## 7. Open questions

1. **Which product is the first consumer?** Therapy is the strongest candidate (patient async messaging + appointment context). Daily-life is a close second (check-ins). Mailing is the weakest (one-shot campaigns don't need conversation memory). Decided by user before Phase 10.
2. **Is `noctusai_lib/llm/audio.py` + `vision.py` already there?** Phase 0 audits. If not, scope sub-task in Phase 1.
3. **Do we keep the bot's pt-BR system prompt as a reference?** Recommendation: **no** — system prompts are product-specific. The seed framework provides the structure; products supply the prose. Decided in Phase 5.
4. **Idle-summary on by default or opt-in?** Recommendation: **opt-in** — every product has different summary needs, and an always-on summarizer adds OpenAI cost the consumer didn't ask for. Decided in Phase 6.
5. **Race fix in debounce ZSET — same project or follow-up?** Recommendation: **follow-up** per §2 constraint (preserve validated shape). File `projects/conversation-buffer-race-fix/` after Phase 10.
6. **Localization (folded sibling idea).** Recommendation: out of scope for this lift — the framework should be locale-neutral; first product consumer (imobi-scheduling) ships pt-BR-only. When a second-language consumer surfaces, file a `projects/conversation-i18n/` follow-up that adds a `language` parameter to dispatcher + per-language prompt template loading. Decided per consumer.

---

## 8. Dependencies & blockers

- **`projects/llm-tool-call-audit/`** must complete before this project's Phase 10, or the chatbot framework ships without audit persistence. Blocking only for end-to-end completeness; library lands without it.
- **`projects/mcp-server-expansion/`** is independent in execution but should land in the same window — products wiring WhatsApp will likely also want the MCP toolkit (Calendar / Maps / send_text) the bot used.
- **Redis available in target product environments.** Check before first-product wiring; not a blocker for the absorption itself.
- **OpenAI access** — already in the platform via `noctusai_lib.llm`.

---

## 9. Success criteria

- [ ] All eight sibling test suites listed in §5.1 (Tests row) ported and **green** under `pytest seed/backend/lib/tests/`.
- [ ] `noctusai_lib/integrations/whatsapp/` and `noctusai_lib/domain/conversation/` are import-able and configurable via `configure_*_module(...)` per `KB § PATTERNS/backend.md`.
- [ ] `KB § PATTERNS/whatsapp-chatbot-seed.md` and `KB § PATTERNS/integrations-fake-fallback.md` exist and are linked from `CLAUDE.md §3` and `KB § INDEX.md`.
- [ ] No product is broken by the lib additions (`pytest products/*/backend/`).
- [ ] First-consumer follow-up project scaffolded.

---

## 10. How to use this plan

- Single source of truth for the WhatsApp absorption.
- Live-tick `[ ]` → `[x]` immediately when a sub-task is done.
- Phase-by-phase by default; user controls cadence.
- §5 there→here map IS the checklist of files to move; every row is verified during its phase.
- Update §11 every phase close.

Useful commands:

```bash
# Sibling reads (read-only — never edit there from this session)
cd ~/Documents/repository/NoctusAI/whatsapp-google-scheduling
ls app/services/ app/workers/ app/api/

# Local lib + tests
cd ~/Documents/repository/NoctusAI/noctusai
pytest seed/backend/lib/tests/

# KB sync verification (must pass before any commit)
bash scripts/verify-kb-sync.sh

# Keeper observation
python mcp/noctusai/cli.py --review
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after multi-turn absorption-evaluation conversation with rapha (sibling repo `whatsapp-google-scheduling` analyzed end-to-end; user confirmed bring-everything-no-skips + seed-feature wiring + two-namespace split). | claude-opus-4-7 |
| 2026-05-03 | Folded sibling's `idempotency-keys` idea into Phase 2 (WAHA `provider_message_id` already in plan) + Phase 7 (Calendar `requestId`). Folded sibling's `google-oauth-activation` runbook lessons into Phase 7 (OAuth refresh-token persistence). First-consumer follow-up project (was Phase 10 open question) supplanted by `projects/imobi-scheduling-bot-creation/` — that product is the named first consumer. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) WILL BE DELETED by the user once the absorption batch is complete:

- **All sibling-path references in this PROJECT.md are execution-scoped.** This project folder gets deleted on close per apply-inline-then-delete; sibling refs vanish with it.
- **No KB doc landed during this project may reference sibling paths.** `KB § PATTERNS/whatsapp-chatbot-seed.md` and `KB § PATTERNS/integrations-fake-fallback.md` (Phases 7 + 9) describe our lib only.
- **No tests reference sibling fixtures.** Tests ported from sibling are rewritten against our lib's data shape.
- **No `pyproject.toml` references sibling.** `noctusai_lib` is the only declared dep for the absorbed code.
| 2026-05-03 | Folded sibling `idempotency-keys` idea (WAHA `provider_message_id` already in §6 Phase 2; Calendar `requestId` added to §6 Phase 7). Folded sibling `google-oauth-activation` lessons into §6 Phase 7 (OAuth runbook surfaces in the consumer product, not in the lib). Added §12 No-leftovers constraint. Cross-referenced new product project `imobi-scheduling-bot-creation` as the natural first consumer (no longer "decided later"). | claude-opus-4-7 |
