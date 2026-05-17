---
slug: whatsapp-chatbot-service
origin: products/youtube-crawler/backend/app/services/whatsapp_chatbot_service.py
intended_noc_destination: noctusai_lib/domain/chatbot/openai_orchestrator.py
layer_rationale: |
  Six-layer model: this is a `domain` primitive (LLM-tool orchestration
  loop) NOT an integration adapter. The WAHA-specific bits (Redis key
  shape keyed on phone, intake delegate) come from the consumer; the
  loop itself (system prompt + tool dispatch + memory) is generic.
  Lifting belongs near `noctusai_lib.domain.chatbot` alongside the
  scheduling / metas primitives.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Every product that needs
  conversational tool-orchestration (mailing, daily-life, therapy,
  ERP triage) can reuse this loop.
  Q2 — Variance across consumers? Tool surface varies (each product's
  intake methods differ); the loop shape (system prompt + memory +
  tool dispatch + max iterations) does not.
  Q3 — Existing seed coverage? Partial — `noctusai_lib.domain.chatbot`
  exists per KB § PATTERNS/whatsapp-chatbot-seed.md but ships a
  template-method base, not an OpenAI tool-calling orchestrator.
  Q4 — Fake+Real shape? Needed: Fake = deterministic scripted reply;
  Real = AsyncOpenAI. Currently inlines AsyncOpenAI; Fake missing.
  Q5 — Migration cost? Low — caller passes (intake, model, api_key,
  redis_client, session_id); WAHA router replaces phone with session_id.
  Q6 — Risk of premature seed lift? Low — N=1 today (WAHA chatbot),
  N=2 incoming (platform chat router shipping in next branch).
dependencies_on_other_additions: []
promoted_on: not-yet
---

## Why this addition exists

Phase 5 ships a WhatsApp chatbot that routes inbound messages through
OpenAI tool-calling. The platform needed a Python orchestration loop
that: (a) holds short-term memory in Redis, (b) exposes 5 tools that
delegate to `WhatsAppIntakeService`, (c) iterates until the model emits
a final text reply or hits the tool-iteration cap. The seed
`noctusai_lib.domain.chatbot` template-method base did not cover the
OpenAI tool-calling shape, so this lands in the product first.

## Integration notes for noc-side

When the platform chat lands (next branch) this becomes N=2 — promote.
Promotion steps:

1. Move file to `noctusai_lib/domain/chatbot/openai_orchestrator.py`.
2. Rename `WhatsAppChatbotService` → `OpenAIToolOrchestrator`.
3. Rename `phone` parameter → `session_id` (already an opaque key).
4. Extract the system prompt into a constructor arg — products vary it.
5. Extract the `_build_tools` block into a Protocol the consumer
   implements (`ChatbotIntake` with `lookup_property`,
   `prepare_upload_request`, etc.) so the orchestrator stays generic.
6. Ship a `FakeOpenAIOrchestrator` that replays canned tool calls for
   tests — mirrors the integrations Fake+Real factory pattern.
7. Update WhatsApp router + new platform chat router to consume from
   the lib.
