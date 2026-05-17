---
slug: platform-chat-agent
origin:
  - products/youtube-crawler/backend/app/services/chatbot_service.py
  - products/youtube-crawler/backend/app/routers/chat_router.py
  - products/youtube-crawler/backend/tests/services/test_chatbot_service.py
  - products/youtube-crawler/frontend/src/pages/Chat.tsx
  - products/youtube-crawler/frontend/src/hooks/useChat.ts
intended_noc_destination:
  - noctusai_lib/domain/chatbot/openai_orchestrator.py  (chatbot_service.py)
  - noctusai_lib/api/chat_router.py                     (chat_router.py)
  - noctusai_lib/frontend/components/Chat.tsx           (Chat.tsx + useChat.ts)
layer_rationale: |
  Six-layer model:
  - `chatbot_service.py`: domain orchestrator (LLM tool-calling loop +
    Redis memory + session abstraction). Belongs in
    `noctusai_lib.domain.chatbot` alongside the scheduling primitive.
    Supersedes the earlier whatsapp-chatbot-service promotion candidate
    by being surface-agnostic from day one.
  - `chat_router.py`: HTTP adapter — sits in the `api` layer. The
    multipart+file-staging shape is a noc-wide pattern (every product
    with a chat surface needs it).
  - `Chat.tsx + useChat.ts`: presentational + hook layer — candidate for
    `noctusai_lib/frontend/components/Chat` once shadcn UI deps are
    absorbed into the lib (the N=4 absorb candidate flagged in
    findings.md Phase 2).
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Every product with conversational
  surfaces (mailing, daily-life, therapy, ERP triage) benefits from
  the same chat shell + chatbot loop + file-attach contract.
  Q2 — Variance across consumers? Tool surface varies (each product's
  intake has different methods); UI/UX shell stays constant — message
  thread + paperclip + reset are universal.
  Q3 — Existing seed coverage? Partial — `noctusai_lib.domain.chatbot`
  ships a template-method base but no OpenAI tool-calling orchestrator
  yet; no chat router/UI in the lib.
  Q4 — Fake+Real shape? Needed for the orchestrator (Fake = scripted
  tool calls; Real = AsyncOpenAI). The router can use the same Fake
  intake from tests/services/test_chatbot_service.py.
  Q5 — Migration cost? Low — consumer plugs an intake (Protocol) +
  session_id + memory keys; orchestrator already takes those via
  constructor args.
  Q6 — Risk of premature seed lift? Low — N=1 (this product) shipping
  with two surfaces (WhatsApp + platform chat). Lift when a second
  product needs the same shell shape.
dependencies_on_other_additions:
  - whatsapp-chatbot-service
  - waha-response-registry
promoted_on: not-yet
---

## Why this addition exists

The WhatsApp chatbot (commit 9948b60) shipped as the first agentic
surface. Users also wanted to talk to the same agent from the product
UI — a Chat page that accepts a property code + optional video file,
fetches CRM data from Vista, and queues the YouTube publish through
the same upload pipeline.

The cleanest path was to generalize the existing chatbot service into
``ChatbotService`` keyed on an opaque ``session_id`` (WhatsApp passes
the phone JID, the platform passes ``web:<uuid>``) and add a new tool
``prepare_upload_from_file`` for the attached-file path. The intake
service gained a Redis-backed file registry so the chat router can
stage a multipart upload before the user decides to confirm.

The platform chat is intentionally unauthenticated for the first
delivery — the frontend route is auth-gated, and a proper JWT-derived
org_id will be wired in a follow-up.

## Integration notes for noc-side

When promoting:

1. Move ``chatbot_service.py`` →
   ``noctusai_lib/domain/chatbot/openai_orchestrator.py``. Rename
   ``ChatbotService`` → ``OpenAIToolOrchestrator``. Extract the system
   prompt into a constructor arg (per-product variance). Define a
   ``ChatbotIntake`` Protocol the consumer implements.
2. Move ``chat_router.py`` → ``noctusai_lib/api/chat_router.py`` as a
   factory (``make_chat_router(intake_factory, settings)``) so each
   product mounts its own with its own intake.
3. Move ``Chat.tsx`` + ``useChat.ts`` →
   ``noctusai_lib/frontend/components/Chat/``. Resolve shadcn UI peer
   deps in the lib (depends on the open shadcn-absorb-N4 follow-up).
4. The file registry stays per-consumer (each intake owns it) until a
   second product needs the exact same shape — then lift to
   ``noctusai_lib.domain.chatbot.file_registry``.
5. Tests in ``tests/services/test_chatbot_service.py`` are the
   reference contract for the Protocol — copy them to the lib's tests
   and parametrize over Fake/Real intakes.
