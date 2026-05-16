---
slug: multimodal-stack
origin:
  - products/youtube-crawler/backend/app/services/media_service.py
  - products/youtube-crawler/backend/app/services/message_store.py
  - products/youtube-crawler/backend/migrations/007_conversation_messages.sql
intended_noc_destination:
  - noctusai_lib/integrations/media/inbound_resolver.py  (media_service)
  - noctusai_lib/domain/chatbot/message_store.py        (message_store)
  - noctusai_lib/domain/chatbot/migrations/conversation_messages.sql
layer_rationale: |
  Six-layer model:
  - `media_service`: domain primitive that turns inbound media into
    text the chatbot can reason about. Belongs in
    `noctusai_lib.integrations.media` (already has the integrations
    layer for downloads + LLM dispatch). Surface-agnostic — same code
    serves WAHA inbound + platform chat uploads.
  - `message_store`: domain primitive — durable audit + UNIQUE-driven
    idempotency oracle. Belongs alongside ChatbotService in
    `noctusai_lib.domain.chatbot`.
  - migration 007: schema artifact, ships with the chatbot lib once
    promoted.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Every product with a
  conversational surface (mailing, daily-life, therapy, ERP triage)
  benefits from media-aware inbound + durable persistence.
  Q2 — Variance across consumers? Audio/image/video resolvers are
  universal; only the document-extraction prompt is product-specific
  (we use a real-estate framing). Easy override via constructor arg.
  Q3 — Existing seed coverage? noctusai_lib.integrations.llm ships
  audio/vision/embeddings building blocks; no `media_service`
  composes them yet. Closing this gap is part of the promotion.
  Q4 — Fake+Real shape? Real = OpenAI Whisper/vision; Fake = canned
  transcript/description for tests. Already mirrors the structure
  whatsapp-scheduling uses.
  Q5 — Migration cost? Low — constructor takes provider-agnostic args
  (base_url, api_key, models); each consumer wires its own settings.
  Q6 — Risk of premature seed lift? Low. N=1 today (this product),
  N=2 once mailing or daily-life adopts WhatsApp.
dependencies_on_other_additions:
  - whatsapp-chatbot-service
  - platform-chat-agent
  - waha-response-registry
promoted_on: not-yet
---

## Why this addition exists

The bot was rejecting any inbound that wasn't text, and the chatbot's
SYSTEM_PROMPT was telling users "I have these other capabilities but
no tool here" — which the user (correctly) pointed out is a lie
when those capabilities are seed-level primitives the product
already has access to.

Three landings:

1. **media_service** — single boundary that downloads from WAHA,
   routes by mimetype, and produces enriched text the chatbot reads
   as a normal user message. audio→Whisper, image→vision,
   video→ffmpeg-extract+Whisper, pdf→pdfminer+summary.

2. **message_store** — `youtube_crawler.conversation_messages` table
   with `UNIQUE(provider_message_id)` driving WAHA dedup. Mirrors
   whatsapp-scheduling's `ConversationMessage` model + IntegrityError
   catch. Replaces a fragile Redis SETNX shim that didn't survive
   restarts.

3. **truthful SYSTEM_PROMPT** — explicit capability list (audio,
   image, video, document, chat, upload) so the bot stops claiming
   features it has and stops claiming features it doesn't.

## Integration notes for noc-side

When promoting:

1. Move `media_service.py` →
   `noctusai_lib/integrations/media/inbound_resolver.py`. Extract the
   product-specific document prompt into a constructor arg.
2. Move `message_store.py` →
   `noctusai_lib/domain/chatbot/message_store.py`. Migration ships
   alongside as part of the chatbot seed lib (each consumer applies
   it on their own schema).
3. Add a `FakeMediaResolver` that returns canned transcripts/
   descriptions — mirrors the seed's other Fake+Real pairs and is
   essential for tests that don't want to hit OpenAI.
4. Add a `FakeMessageStore` (in-memory dict keyed on
   provider_message_id) for the same reason.
