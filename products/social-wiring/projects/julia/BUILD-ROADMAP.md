# Lais module — build roadmap (our own agent inside social-wiring)

Status 2026-10-14 (evening): **page 0 (Julia) is LIVE in prod** (`2ca3372b5`; agents 024–026 + SW 255/258/259 applied) — off until the owner's setup (`TEST-CHECKLIST.md`). The agent lives in the `agents` product; SW integrates via API and its pages mirror Lais (`specs/julia-agent-contract.md`, v3 §11). Pages 6–13 (Notificações, Conversas v2, Captação, Painel, Relatórios, Distribuição, Cloud-API pages, Avaliações/CAPI) and the full Lais→SW route map are in `specs/sw-reconstruction-map.md`; the authoritative Lais map is `[private study: page-map-v2]` + `[private study: mechanisms]`.
Cadence (same as CoreStudio → Criação de Mídia): per page → contract (`specs/<page>-contract.md`) →
BE/FE waves in worktrees → gates on merged dev → release → owner tests in prod → next page.
Reference: `[private study: agent-brain]` (what Lais does), `[private study: bubble-app-definition]` (their forms),
`DECISIONS.md` (WAHA now / Cloud API later; own number; qualified leads go into SW; "Lais" is a temporary name).

## What already exists (reuse, don't rebuild)
- WhatsApp transport + inbox: WAHA webhook `routers/whatsapp_router.py` → `MessageStore` / `whatsapp_chats` / realtime SSE; seed `integrations.whatsapp` (WahaClient; MetaCloudClient send_text only).
- Seed conversation plumbing: `domain.chatbot` buffer (debounce + idle ZSET), worker, `delivery.split_reply`, `summary.summarize_conversation` (structured output).
- Seed LLM layer `integrations.llm` (anthropic/openai/gemini/fake, budget, usage) — **no tool calling yet**.
- Agent Studio prompt compiler (`products/agents/backend/app/studio/compiler.py`): pure, deterministic, hashed — typed sections → system prompt.
- Lead → card: `leads_service.create_lead` + `attach_lead_now` → trigger `spawn_funil_card` creates the atendimento.
- Timers: seed `domain.jobs` (`scheduled_for`, `RescheduleLater`). Visits: seed `domain.scheduling.SchedulingEngine`, `sched_*`, `agendamentos`, `roteiros/visitas`.
- UI: nav group `src/nav/lais.ts`, `pages/lais/{Conversas,Configuracoes}.tsx` over `WhatsAppWorkspace` + seed `ChatWindow`.

Not reused: the current bot (`ChatbotService`, "One Chat") is an **operator** assistant (whitelist, upload/Drive/Calendar tools, `AsyncOpenAI` directly). The lead agent is a separate mode, never a branch inside it.

## Pages
| # | Page (sidebar Lais ›) | Delivers | Main pieces |
| --- | --- | --- | --- |
| **0** ✅ LIVE | **Agente** (agent lives in `agents`; SW page = link + routing) | Julia, a lead-facing bot (see `specs/julia-agent-contract.md`; supersedes the SW-local runtime described in this row) that answers on one chosen WhatsApp connection, plus a "Testar conversa" simulator. Everything after is testable end to end. | **Seed:** provider-neutral tool calling in `integrations.llm` (`chat_with_tools` → normalized ToolCall/ToolResult; openai + anthropic + fake), `LLMDispatcher` rebased on it; lift Agent Studio's `compile_prompt` (+ section/skill models, `prompt_hash`) to `noctusai_lib.domain.agent_prompt` (agents re-imports; pilot agents → SW). **SW:** per-connection `agent_mode ∈ {operator, lead}` (default operator; explicit, strictly tested), `LeadAgentService` branched after the buffer in `_process_waha_body`; persona (name, tone, greeting), provider/model (default OpenAI until the Anthropic limit clears 2026-11-01), on/off per connection, per-chat pause ("Lais atendendo" / manual) visible in Conversas. Fix-on-contact: `ChatbotService` moves off `AsyncOpenAI` onto the same seam. LGPD flag (lead conversations: retention + consent text). |
| 1 | **Conhecimento** (Meu negócio) | Typed knowledge sections compiled into the prompt on publish (versioned, hashed, cached in SW). | Sections from `[private study: bubble-app-definition]` §4: Geral (políticas, telefones por setor, exibir nome do atendente, recesso), Vendas (operação, documentos, financiamento), Locação (operação, documentos, processo, garantias), WhatsApp profile text. Draft → publish → recompile; preview of the compiled prompt. |
| 2 | **Perguntas essenciais** | Slot catalogue + per-conversation slot state; qualifying flag. | Versioned catalogue (label + LLM hint + category + operation scope); limits (max active / max qualifying; one required = comprar ou alugar); extraction via `summarize_conversation` with a consumer `output_schema` (no new extractor); slot panel in Conversas. |
| 3 | **Envio ao SW** | Qualified lead → SW lead + card, idempotent per phone; plus Lais' three policies: potential captações, cold leads, invalid WhatsApp. | Rules (OR of AND criteria: qualifying slots filled, visit requested, value range); triggers `qualified` / `conversation-ended` / `cold-timer`; new `lead_sources` slug for the agent; `create_lead` idempotent per phone (else `spawn_funil_card` duplicates cards); link chat ↔ cliente; AI summary into the card. |
| 4 | **Reengajamento** | Two-tier follow-ups. | Short tier (any hour, 5–60 min) + long tier (business hours, 1–11 h) on `domain.jobs`; cancel pending jobs on inbound; never after explicit close; message texts (WAHA = free text; Cloud API templates later); cold-lead push after last attempt (page 3 rule). |
| 5 | **Visitas** | Pre-scheduling from the chat. | Agent tool proposes slots from `SchedulingEngine` with a broker-availability source; pending visit linked to lead/atendimento; config: days/hours per weekday, buy/rent split, min/max window, CPF required. |

Later (not scheduled): templates registry (needed for Cloud API), broadcasts/remarketing, reports, Google reviews, credit analysis.

## Risks
1. The page 0 seed slice touches every LLM provider → contract-first, fake provider first, proved on the One Chat migration.
2. Mode routing on the shared WAHA path: an error exposes operator tools to a lead → explicit field, default operator, strict tests.
3. Lead conversations are personal data → LGPD flag at page 0.
4. Lifting the compiler collides with one-ops-agents Phase F (C2) → sequence the lift before Phase F resumes.
5. The Anthropic account is at its monthly limit until 2026-11-01 → default provider OpenAI, switchable by config.

## Owner questions before page 0
1. Confirm order 0 → 5 (page 0 added so the bot exists before its settings).
2. Which WhatsApp connection/number is ours for the lead agent (WAHA session)?
3. Persona: name shown to leads while the module is called "Lais" (the real Lais keeps its own number — same name on two numbers may confuse leads).
4. Provider: OpenAI as default until 2026-11-01, then switch to Anthropic?
