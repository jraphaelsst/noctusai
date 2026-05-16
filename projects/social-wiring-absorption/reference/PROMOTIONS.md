# Promotion Manifest — noctusai-youtube-crawler

Index of additions in this seed workspace that are candidates for
promotion into noc. One line per entry; full metadata in
`.promotions/<slug>.md`.

Format mirrors `MEMORY.md` — pointer-only, ≤150 chars per line.

See KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md § Promotion manifest.

## Pending

- [whatsapp-chatbot-service](.promotions/whatsapp-chatbot-service.md) — OpenAI tool-calling loop with Redis memory; lift to `noctusai_lib.domain.chatbot.openai_orchestrator` at N=2.
- [waha-response-registry](.promotions/waha-response-registry.md) — captures WAHA response shapes for drift detection; lift to `noctusai_lib.integrations.whatsapp.response_registry`.
- [platform-chat-agent](.promotions/platform-chat-agent.md) — surface-agnostic ChatbotService + chat router + Chat UI; supersedes whatsapp-chatbot-service. Lifts as `noctusai_lib.domain.chatbot.openai_orchestrator` + chat router factory.
- [multimodal-stack](.promotions/multimodal-stack.md) — media_service (audio/image/video/pdf resolver) + message_store (UNIQUE-driven dedup) + truthful SYSTEM_PROMPT; lifts into `noctusai_lib.integrations.media` + `noctusai_lib.domain.chatbot.message_store`.
- [single-url-tunnel](.promotions/single-url-tunnel.md) — reverse-proxy + frontend nginx SPA fallback + runtime-smart apiBase() so one tunnel URL serves the whole stack; lifts into seed-workspace-docker template + product-seed frontend + `noctusai_lib.frontend.lib.apiBase`.
- [google-integrations](.promotions/google-integrations.md) — Calendar (Fake + ServiceAccount + OAuth) + Routes/Maps + Drive-URL-inspect ported from whatsapp-google-scheduling; lifts into `noctusai_lib.integrations.google.{calendar,routing}` + a factory chat-tool surface for any seed-adopting product.
- [drive-api-client](.promotions/drive-api-client.md) — real Drive API v3 read client (search/list/get) + 3 chatbot tools; reuses Calendar OAuth credential bundle (drive.readonly bundled into the scope); lifts into `noctusai_lib.integrations.google.drive`.

## Promoted

_(none yet)_
