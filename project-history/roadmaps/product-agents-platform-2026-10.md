# product-agents-platform-2026-10 — one guardian agent per product, served by the agents platform

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: owner interview 2026-10-07. Each product's MASTER-PROMPT becomes the prompt that creates that product's agent.
> Decision: **ship the design record now (Phase 1). Build P0→P6 in sequence; the P1 security project runs in parallel.**
> Consumption split (D10, restated by owner 2026-10-07): **Claude Code consumes agent packages from LOCAL FILES** (no API calls, to save tokens). **The routing API is for app usage only** (bubble, One Chat, agent↔agent) until further decision.

## Origin

The owner wants every product to have **one specialist agent**: the product's *guardian*. It knows the product's architecture, stack, specs, infra, dataflow, processes and, later, its business model. The same agent is used in two places:

- **(a)** by Claude Code, which loads it and impersonates it whenever it works on that product;
- **(b)** by the product's **chat bubble**, as the assistant for logged-in users.

Agents live in the `agents` product (internal, admin-only). Other products reach them through an **internal-only routing API**. Every conversation is stored in the `agents` schema. The owner made shielding a first-class requirement. Our own corestudio study (`products/social-wiring/projects/core-studio/`) showed five leak classes in a peer product: system prompts served to the client, IDOR, prompt payloads readable by users, tokens in SSR HTML, and state-changing GETs. We must not ship any of them.

Delivery order (D-SEQ): business-interviewer agent and the agent-creation method first. Then the platform core, the bubble, the SW assistant, the seed agent generalized and validated on igig, and the generic helper.

## Current state — evidence at `origin/dev` b4e1d8536 (2026-10-07)

| Area | Finding | Path |
|---|---|---|
| agents product | **Live in prod and substantially built.** Agent Studio (sections / skills / knowledge / evals / versions / compiled prompts / bundle import `noctus.agent-bundle/v1` / repo packages `noctus.agent-package/v1`), Julia on the Claude Agent SDK with an approval gate, public_ask, 19 migrations in schema `agents` | `products/agents/backend/app/` |
| agents docs | 🔴 **Drift**: README + MASTER-PROMPT say "scaffold, PLANNED"; config.py comment contradicts `_launch_env` | `products/agents/{README,MASTER-PROMPT}.md`, `app/config.py:84` |
| agents prompt exposure | 🔴 `GET /api/studio/prompts/{hash}` returns the compiled prompt to **any org member** | `routers/studio_agents_router.py:851` |
| agents seams | Single-agent pins (`JULIA_KEY`, `get_by_key("julia")`, `_JULIA_DIR`) | `conversations_router.py:86,245`, `persona_router.py:53` |
| agents cost | Cost stored per message, but **no org budget**; agents is missing from `_PRODUCT_SCHEMAS`; a missing key silently falls back to `FakeAgentRuntime` | `runtime/__init__.py:109` |
| help-chat bubble | Seed module exists (`noctusai_lib.domain.help_chat` + `HelpChatBubble`), but **only igig consumes it**. Prompt is a 3,339-line file (`guia-igig.md`) loaded at boot; no history; `pagina_atual` accepted but never used; no "don't reveal" rule; in-memory per-process rate limit | `seed/lib/backend/noctusai_lib/domain/help_chat/`, `seed/lib/frontend/src/components/help-chat/` |
| igig negócio assistant | Hardcoded prompt, Sonnet, nothing persisted | `products/igig/backend/app/services/assistente.py` |
| SW chatbot = **One Chat** | Product-local `ChatbotService`, **direct OpenAI `gpt-4o-mini` SDK calls** (no ledger, no budget), persona hardcoded as a constant, 23 tools, Redis memory with 1h TTL. The agents product only *lists* it and toggles auto-reply over the `agents-bridge` | `products/social-wiring/backend/app/services/chatbot_service.py` |
| SW `/api/chat` | 🔴 **Public, unauthenticated, no rate limit.** Runs as the default org with real tools (Drive, Calendar, YouTube queue, Meta, 500 MB uploads). Owner chose to fix it in P4, not as a hotfix (D-HOTFIX) | `routers/chat_router.py`, `frontend/src/App.tsx:523` |
| SW WAHA webhook | HMAC skipped when the secret is unset; an empty `authorized_numbers` allows everyone | `routers/whatsapp_router.py:891,951,224` |
| Rate limiting | 🔴 Seed default `100/minute` is **dead**: no product installs `SlowAPIMiddleware`; only explicitly decorated routes are limited | `noctusai_lib/api/rate_limit.py:54` |
| Internal auth | Only per-product `pk_*` opaque tokens + `X-Approval-Assertion` JWS + HMAC webhooks. **No generic internal-call identity** | `noctusai_lib/api/auth/session/api_tokens.py`, `products/agents/backend/app/runtime/assertion.py` |
| AI cost visibility | `llm_usage` exists only for erp/therapy/social_wiring; igig has none; SW chatbot/media bypass it; budget is fail-open | `noctusai_lib/integrations/llm/budget.py:56` |
| MASTER-PROMPT gate | `verify_master_prompt` only checks router filenames (its second check is dead code); **no keeper/hook/CI runs it** | `mcp/noctusai/tools/noctus/dev/master_prompts.py:64,100` |
| Overlapping plan | `projects/one-ops-agents` D7/D8 (One Chat moves into agents; Phase F on hold). **This roadmap supersedes D8/Phase F** — see open question Q5 | `projects/one-ops-agents/PROJECT.md` |

## Locked decisions (owner interview 2026-10-07; LOCKED, not assumptions)

### Agent definition, sync, knowledge
| # | Decision |
|---|---|
| D1 | **One agent per product = its guardian**: architecture, stack, specs, infra, dataflow, processes (lead → sale → post-sale), and later its business model |
| D2 | **Source of truth = git package** `products/agents/packages/<slug>-assistant/` (`noctus.agent-package/v1`). Deploy builds it and publishes it to the agents DB. **Two-way sync, split by section**: each section has one owner (git or UI), so concurrent edits to one section cannot happen by construction |
| D3 | Conflict fallback (ownership change / split violated): an **Anthropic API call reconciles** the versions; the result lands as a reviewable change, never silently |
| D4 | `products/<slug>/MASTER-PROMPT.md` is **generated** from the package's `specs` section (existing tooling keeps working) |
| D5 | **Canonical section schema** (seed agent), with audience view + owner per section. The table follows below |
| D6 | **Knowledge = router, not blob.** Like CLAUDE.md: the core prompt is a router of **addresses** (`<slug>/<section>/<doc>#<anchor>`) pointing at addressed docs, loaded on demand. **Semantic chunk search is the fallback only.** The gate checks that every address resolves and that no doc is orphaned |
| D7 | **Two compiled views per agent.** *Guardian view* (everything) compiles **only** for Claude Code local use and admin tools. *Bubble view* compiles **only** user-safe sections. What is not in the bubble prompt cannot leak (the owner rejected "one prompt + guardrails" as violating no-exposure) |
| D8 | **Layered composition**: **core agent** (maintained in agents; e.g. a generic chatbot + tools) + **product layer** (product-specific specs) + **org layer** (per-customer specs). Precedence **core > product > org**. Org layers are authored **only by NoctusAI admins**, compiled as fenced DATA, and can never override core security/limits |
| D9 | Agent-to-agent calls are **built in this increment**, through the routing API with the same auth, scoping and cost tracking |

**D5 · canonical section schema**

| # | Section | Bubble | Guardian | Owner |
|---|---|:-:|:-:|---|
| 0 | `router`: address map (auto-generated) | ✓ safe subset | ✓ | generated |
| 1 | `identidade`: mission, persona, tone | ✓ | ✓ | UI |
| 2 | `limites`: secrecy (prompt / model / provider / infra never revealed), scope, PII, injection handling | ✓ | ✓ | git |
| 3 | `produto`: what it is, audience, value | ✓ | ✓ | git |
| 4 | `jornada`: onboarding, how-to per page | ✓ | ✓ | git |
| 5 | `processos`: e2e playbooks (one doc per process, H2 per stage) | ✓ user-safe | ✓ | git |
| 6 | `dados-do-usuario`: what it may read via tools | ✓ | ✓ | git |
| 7 | `faq-e-problemas`: troubleshooting | ✓ | ✓ | UI |
| 8 | `escalonamento`: handoff / insights / feedback rules | ✓ | ✓ | UI |
| 9 | `negocio`: business model, cashflow | ✗ | ✓ | git |
| 10 | `arquitetura`: stack, modules, seed seams | ✗ | ✓ | git (derived) |
| 11 | `dados-e-fluxos`: schema, dataflow, integrations | ✗ | ✓ | git (derived) |
| 12 | `api`: endpoints | ✗ | ✓ | git (derived) |
| 13 | `infra`: deploy, containers, env, ports | ✗ | ✓ | git (derived) |
| 14 | `seguranca`: threat model, gates, known risks | ✗ | ✓ | git |
| 15 | `specs`: today's MASTER-PROMPT content → generates MASTER-PROMPT.md | ✗ | ✓ | git |

Sections are added only when their capability exists (no placeholder sections, per no-incomplete-commits). `negocio` stays absent until the biz agent's work produces it.

### Claude Code usage
| # | Decision |
|---|---|
| D10 | Claude **loads the package locally and impersonates the agent** (its context + the agent's), with no API call. Load policy: **guardian core always** (on contact with `products/<slug>/`) **+ depth on demand** via addresses (MCP tool or package files) |
| D11 | Freshness gate = **warn on commit + block deploy** while the product's agent is stale (derived sections out of date, or product code changed after the last agent-reviewed mark) |

### Bubble (seed organ, every product)
| # | Decision |
|---|---|
| D12 | The bubble is **absorbed into the seed + product template**. Products differ only by agent context |
| D13 | **Logged-in users only** |
| D14 | v1 capability: **read the user's own data**. Access = **delegated user identity** (short-lived signed token carrying user + org + read-only scope) **through curated per-product agent-tool endpoints** (never the full product API, never service-role) |
| D15 | Products without a published agent show the **generic NoctusAI helper** (its own package) |
| D16 | Language: **follow the user** (knowledge stays pt-BR) |
| D17 | Conversation UX: chat screen ← back-arrow → list of the user's conversations; "new conversation" button on the list screen. **A conversation is persisted only when its first message is sent**; every user and agent message after that is recorded |
| D18 | The ℹ️ hover (mode / provider / model) shows **only to NoctusAI admins**. Agents **never disclose their model/provider** when asked (`limites`) |
| D19 | Escalation: **notify + ticket + reply in the bubble** (admins answer from the agents product as "Equipe NoctusAI"; the agent pauses on that thread until released). Also an **improvement/insights queue** and **👍/👎 per answer** |
| D20 | Escalation + security alert recipients: **owner + NoctusAI admins** (configurable list) |

### Runtime + models
| # | Decision |
|---|---|
| D21 | Per-agent runtime config, simple selection in agents: **mode** `Rápido` (Messages-API chat runtime, prompt-cached, tools, budgeted) \| `Agente` (Claude Agent SDK) × **provider** (Anthropic \| OpenAI) × **model** |
| D22 | One Chat **switches to Claude** on the move. The model/price comparison (looked up live, not from memory) is shown to the owner before cut-over |

### Storage, history, cost
| # | Decision |
|---|---|
| D23 | Conversation history in the **`agents` schema**. Every conversation is a DB object linked to **agent + user and/or contact + org + product**. Raw and kept (retention deferred; the system is strictly closed) |
| D24 | One Chat (WhatsApp end customers) conversations use the **same history model**, keyed by contact |
| D25 | **AI usage ledger: central** (e.g. `public.ai_usage`, append-only, service-role write) fed by the seed LLM client for **every** product. Tokens + USD per provider / model / product / feature / org / user. Dashboard in **core admin**; replaces the per-product `llm_usage` tables (data migrated). Every cost relation is visualized |
| D26 | **Keeper blocks direct `openai` / `anthropic` SDK imports** in `products/` (only the seed LLM client + agents runtime may import them) → every call is tracked and budgeted by construction |
| D27 | Platform key pays for the bubble. **Caps: global (Noctus) ≥ org ≥ user**, each optional (unset = unlimited, always bounded by its parent). A cap can be consumed by one child or shared by N. **Product = reporting dimension, not a cap level.** Windows **daily + weekly + monthly**, recommended defaults, all configurable. At cap: **block + notify** (alert at 80% and 100%) |

### Security + internal communication
| # | Decision |
|---|---|
| D28 | Routing API is **internal-only**: private docker network, **no tunnel ingress** |
| D29 | Caller proof, layered: **short-lived signed service JWTs** (per-product asymmetric keys, aud=agents, ~60 s, nonce) **+ mTLS** between containers; **`pk_*` tokens** kept for existing bridges |
| D30 | **Future public exposure without refactor**: a separate **public gateway** becomes the only internet-facing piece (external keys, quotas, abuse filtering, output scrubbing). It calls the internal API as one more caller kind. The auth layer models `caller_kind` from day one |
| D31 | Agent internals (sections, compiled prompts, knowledge, history) are visible to **NoctusAI superadmins only**. Everyone else gets **404, not 403**. Every read is audit-logged |
| D32 | **Global rate limiting by default** on every endpoint, present and future (seed-level, opt-out only with a declared reason + keeper). Limiter-store failure: **tiered** (fail closed on auth/LLM/expensive routes; fail open with in-process fallback on ordinary reads) **and the owner is always notified** |
| D33 | Alerts go to **Telegram + WhatsApp (WAHA) + email + in-platform + Sentry** |
| D34 | **Security project (P1) runs in parallel now.** Web research on common → super-rare leak / attack classes + community opinion + vetted libs/tools. Covers IDOR / ownership, secrets / prompts to client, prod build hardening (source maps, state-changing GETs, headers), DDoS, SQL/DB injection, and all classes found. **Code gates + live protection mechanisms** |
| D-HOTFIX | SW `/api/chat` exposure is **folded into P4** (owner decision; no hotfix) |

### Process + sequence
| # | Decision |
|---|---|
| D35 | **Business-design interviewer agent first** (P0): a dev-advisor package + prompt mechanics for Claude's use (not the agents API), **auto-triggered skill**, fed by the owner's video transcript + existing specs. **Do not pre-feed cashflow**; the owner uses it to develop the cashflow, SW first |
| D36 | **Agent-creation method documented** (KB pattern + seed agent template + skill) so agents for any product can be replicated reliably |
| D37 | igig "Assistente do negócio" becomes **a skill of the igig agent** |
| D38 | One Chat outage handling: **queue + retry with backoff + alert** (SW's Redis buffer holds; never a silent drop) |
| D39 | One Chat's 23 tools stay **in SW, scoped by org**, exposed as curated agent-tool endpoints. The generic chatbot core lives in agents; SW contributes the product layer; any future product can reuse the chatbot core with its own layer |
| D-SEQ | Sequence approved: **P0 → (P1 parallel) → P2 → P3 → P4 → P5 → P6** |

## Phase 1 — design record (SHIPPED)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | Interview decision record + target architecture + phase plan | NEW `project-history/roadmaps/product-agents-platform-2026-10.md` | **shipped** | Read-only; no live check needed |

**Behavior guarantee**: no runtime change.

## Target architecture (summary)

```
            git: products/agents/packages/<slug>-assistant/      (sections/, knowledge/<addr>.md, skills/, evals.json, layers/)
                     │  build (compiler: router + 2 views)        ▲ UI-owned sections sync back (split by section)
                     ▼                                            │
   dist/guardian/  ── Claude Code loads locally (core + addresses on demand)
   dist/bundle.json ─ deploy publishes ─▶ agents DB (Studio, versions, knowledge)
                                              │
   product backend ── signed service JWT + mTLS (private net) ──▶ agents ROUTING API ──▶ runtime (Rápido | Agente) × provider × model
        ▲   mints delegated-user token                                │        ├─ compose: core > product layer > org layer
        │                                                             │        ├─ tools ──▶ product agent-tool endpoints (delegated token, org-scoped)
   seed HelpChatBubble (every product) ──▶ product /api/assistant ─────┘        ├─ agent↔agent (same API)
                                                                              ├─ agents.conversations/messages (agent·user|contact·org·product)
                                                                              └─ public.ai_usage ledger ─▶ caps global≥org≥user ─▶ core admin dashboards
   (future) public gateway ──▶ same routing API as caller_kind=external
```

## Phase plan (each phase opens its own PROJECT.md with a Phase-0 audit; gates re-run on the merged tip)

### P0 — business-interviewer agent + agent-creation method (NEXT)
| # | Slice | Verify recipe |
|---|---|---|
| P0.1 | Owner provides video transcript (or video → `llm_audio_transcribe`) + existing specs | Files present at an owner-given path |
| P0.2 | `biz-interviewer` dev-advisor package (router knowledge, interview method distilled from the transcript) | `agent_package_build` emits dist; Claude loads the core + an address on demand |
| P0.3 | Auto-trigger skill (`business model` / `monetize` / `pricing` / `cashflow` phrases) that loads + impersonates it | Trigger phrase in a fresh session activates it |
| P0.4 | KB pattern **agent-creation** + seed agent template package + `noc-new-agent` skill (method v0, refined in P5) | Scaffold a throwaway agent from the template; build passes |

### P1 — security project (PARALLEL, own project folder)
Web research (common → super-rare; community opinion; vetted libs). Then, as gates + live mechanisms: global default rate limit (D32), IDOR / ownership sweep + sequential-id audit, no prompts / secrets / tokens to client (API + SSR + bundles), prod build hardening (no source maps, no state-changing GETs, CSP/headers), injection (SQL / DB / prompt), DDoS posture (edge + app), alerting fan-out (D33). Verify: each gate fails on a planted fixture; limiter returns 429 live; alerts arrive on all 4 channels.

### P2 — agents platform core
Router-knowledge format + compiler emitting 2 views + layer composition; section ownership + two-way sync + Claude reconciler (D3); routing API (internal-only) + `caller_kind` auth (service JWT + mTLS; gateway-ready); delegated-user token; runtime modes `Rápido` / `Agente` × provider; agent↔agent; superadmin-only internals (fix `prompts/{hash}`); de-pin Julia seams; central `ai_usage` ledger + caps + core-admin dashboards; direct-SDK keeper; freshness gate (D11) + MASTER-PROMPT generator; agents README/MASTER-PROMPT drift fix. Verify: a product container calls the routing API on the private net and gets a reply; the same call from outside the network fails; a bubble-view compile contains no guardian-only section (gate).

### P3 — seed bubble + conversation store
Seed bubble v2 (list ↔ chat, persist-on-first-message, 👍/👎, handoff, admin ℹ️), product `/api/assistant` proxy organ, template mount, history tables in `agents`, handoff/ticket/insights UI in agents. Verify: a fresh template product shows the bubble with the generic helper, and a conversation row appears only after the first message.

### P4 — SW assistant + One Chat into agents
`sw-assistant` package (guardian + bubble views; the `processos` deal-documentation playbook drafted by a peer session goes into the package once validated); SW agent-tool endpoints; One Chat = generic chatbot core + SW layer + org layers, Claude model (D22 price check first), queue/retry/alert (D38); SW `/api/chat` behind auth + limits; WAHA HMAC fail-closed; empty allow-list = nobody. Verify: SW bubble answers a deal question from the user's own data; a WhatsApp message round-trips through agents; `/api/chat` without auth → 401.

### P5 — generalize the seed agent → igig assistant
Refine the method from P4 learnings; `igig-assistant` (guia-igig split into addressed docs; negócio as a skill); retire the file-based help_chat path. Verify: igig bubble on agents; the old guide boot-load is gone.

### P6 — generic NoctusAI helper
Package + default for agent-less products. Verify: an agent-less product's bubble answers platform questions without leaking internals.

## Anti-goals

- ❌ Bubble prompts carrying guardian-only sections, "protected" by instructions alone. Rejected by the owner (D7).
- ❌ Any internet-reachable path to the routing API in this increment (D28). Exposure comes only via the future gateway.
- ❌ Customer-authored org layers (D8). Admin-only for now.
- ❌ Retention / deletion policy work now (D23). Deferred by the owner; the system stays closed.
- ❌ Pre-writing cashflow / business-model content into any agent (D35).
- ❌ A second chatbot engine in SW after P4 (D39). One core, many layers.

## Open questions (revisit at the named phase)

- **Q1 (P0) · BLOCKS P0.2+**: another agent transcribes the owner's video. The owner then hands over (a) the full transcript and (b) the "gold" points they extracted. Claude evaluates both: confirms, refines or fixes the gold against the transcript, and only then builds the biz agent. Existing business specs come from the owner at the same time. **Dev stops at P0.1 until this arrives** (owner instruction 2026-10-07).
- **Q2 (P2/P4)**: live model prices (Claude vs gpt-4o-mini) for the D22 comparison + recommended cap defaults (D27). Look up, never from memory.
- **Q3 (P2)**: mTLS operational shape on the VPS fleet (CA, rotation). Decide in the P2 Phase-0 audit.
- **Q4 (P4)**: final validated deal-documentation playbook from the peer session (draft v0.1 at the owner's Downloads, not in repo).
- **Q5 (P2)**: fate of `projects/one-ops-agents` (D7/D8 superseded here; one-ops agent itself and its D1–D6 remain). Owner to confirm absorb vs keep.

## Cost shape change

- **Today**: SW chatbot + media on OpenAI with an env key, untracked; agents on one Anthropic key, unbudgeted; igig on per-org keys, untracked.
- **After P2–P4**: every AI call goes through the ledger with caps; bubbles on the platform key (support cost owned by NoctusAI, capped); One Chat moves to Claude. Delta quantified in Q2 before the switch.

## Decision log

- **2026-10-07**: D1–D39 + D-HOTFIX + D-SEQ locked in an owner interview (11 rounds). Roadmap opened.

## Retrospective

*Filled when P0 ships.*

## Composes with

`KB § PATTERNS/security/llm-bot-security.md` · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `KB § PATTERNS/architect/products-consume-canonical-organs.md` · `KB § PATTERNS/frontend/consent-routes-mandate.md` · `KB § PATTERNS/devops/prod-exposure-consent.md` · `projects/one-ops-agents/PROJECT.md` · `products/social-wiring/projects/core-studio/`
