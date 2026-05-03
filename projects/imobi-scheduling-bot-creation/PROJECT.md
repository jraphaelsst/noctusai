# imobi-scheduling-bot-creation — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update §11.
>
> **Write for a zero-context reader.** Inline context in §1, quote the user in §2, name files with paths in §5, pair every §7 Open Question with an evidence-backed recommendation, make §10 commands copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Design captured → Phase 0 ready (audit + slug confirmation must precede any scaffold)
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § GUIDES/new-product.md` (canonical product creation guide), `KB § 02-LANDSCAPE.md` (existing products + ports), `projects/whatsapp-seed-absorption/PROJECT.md` (this product is its **first consumer**), `projects/llm-tool-call-audit/PROJECT.md` (this product is its **first consumer**), `projects/scheduling-engine-seed/PROJECT.md` (this product is its **first consumer**), `projects/mcp-server-expansion/PROJECT.md` (this product is the **first MCP business-logic-tool client**), templates at `templates/PROJECT-TEMPLATE.md` + `templates/product-seed/`.
- **Project slug:** `imobi-scheduling-bot-creation` — cross-cutting "not-yet-a-product" project per `KB § PATTERNS/project-execution.md §1` (the work itself creates the product; lives at root `projects/<slug>/` until the product exists, then promotes to `products/<product-slug>/projects/`).
- **Target product slug:** `imobi-scheduling` (proposed; **OPEN QUESTION #1** — user confirms or renames before Phase 1).

---

## 1. Context & Purpose

The user has a tested, working WhatsApp scheduling bot at sibling repo `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`. It schedules real-estate content production appointments (media-crew showings of properties for content production: photos, video, drone) routed through Google Calendar, with conversation memory, debounce, idempotency, OAuth/service-account/Fake calendar adapters, Maps routing, audit trail, and unit-tested scheduling rules. End-to-end working MVP.

The user wants this **rebuilt as a NoctusAI product on our own patterns**, freshly implemented — not lifted as a code-port, but reimplemented consuming the seed features the absorption batch is producing. *"We're gonna create this as a noc product, got it? That's what i meant by there->here plan, so we implement the product on own code pattern as it should be, right from fresh start."*

This product is the **first consumer** of three seed efforts landing in parallel:
1. `projects/whatsapp-seed-absorption/` → `noctusai_lib.integrations.whatsapp` + `noctusai_lib.domain.conversation`.
2. `projects/llm-tool-call-audit/` → `noctusai_lib.domain.ai.tool_audit`.
3. `projects/scheduling-engine-seed/` → `noctusai_lib.domain.scheduling`.

…and the **first MCP business-logic-tool client** of `projects/mcp-server-expansion/` Phase 5 (Calendar / Maps / scheduling / WhatsApp send-text under `platform.business.*`).

The new product is built fresh on our patterns: `create_product_app(...)` with seed routers, RLS policies per `KB § PATTERNS/database-rls.md`, tests in three layers per `KB § PATTERNS/testing.md`, `MASTER-PROMPT.md` + `README.md` from day one per `KB § GUIDES/new-product.md`. **None of the sibling's bot code is copy-pasted into the product.** What carries over is the *product semantics* — entities, intents, conversation flows, scheduling rules, integrations — re-expressed on our patterns.

The win: the bot stops being an orphan repo with its own conventions and becomes a first-class NoctusAI product on the seed framework, alongside `erp-imobiliario`, `therapy-platform`, `daily-life`, etc. When it's done, the sibling repo can be deleted with no functional loss.

---

## 2. Confirmed constraints

Decisions the user made in the 2026-05-03 absorption-evaluation session.

- **Bot becomes a noc product, fresh implementation** — *"i want this chatbot project to be created. We're gonna create this as a noc product, got it? That's what i meant by there->here plan, so we implement the product on own code pattern as it should be, right from fresh start."* — Not a code-lift from the sibling. The sibling's product semantics (entities, flows, scheduling rules, intents) reimplement on our patterns. *(Drives §3 principle 1 + §6 phasing.)*
- **First consumer of the absorption-batch seed features** — confirmed via the four sibling projects this depends on. *(Drives §8 dependencies.)*
- **No sibling-folder leftovers post-absorption** — *"im gonna dump both folder after the absorption is complete, so no leftovers, no pointers, no references, nothing. After absorption im gonna erase those folders (me, not you, please hahaha)."* — All sibling-path references in this project are execution-scoped (this PROJECT.md gets deleted on close per apply-inline-then-delete; the product code carries no sibling refs). *(Drives §12.)*
- **Sibling project plans inform scope** — `production-hardening`, `security-hardening`, `cancellation-rescheduling`, `google-oauth-activation`, `admin-surface`, `bulk-import`, `crew-assignment-rules`, `idempotency-keys`, `state-machine-for-requests`, `gpt-confidence-thresholds`, `localization`, `data-retention`, `provider-payload-audit`, `operational-dashboards` — these were sibling planning artifacts. The portable-to-platform ones FOLD into the seed projects (see those PROJECT.md files). The product-domain-specific ones FOLD into THIS project's §6 phases and §7 open questions (admin UI, bulk import, crew rules, end-customer expansion, etc.). *(Drives the product's §6 + §7.)*

---

## 3. Design principles

How we're approaching this specific product creation (beyond `CLAUDE.md` rules).

1. **Fresh implementation, not code lift.** The sibling's `app/services/scheduling_service.py` is not copied into the product. The product imports `noctusai_lib.domain.scheduling.SchedulingEngine`, configures a `SchedulingRules` instance, supplies a real-estate vocabulary (locations = condominiums, assignees = media crew, transition buffer = travel buffer), and is tested fresh. *Why:* the sibling's code was written before the seed feature existed; the seed is the right layer for the engine. The product's code is the wiring + the domain.
2. **Standard product structure per `KB § GUIDES/new-product.md`.** `products/<slug>/{backend, frontend, README.md, MASTER-PROMPT.md}` from day one. Backend uses `create_product_app(...)` with `standard_routers=[..., "whatsapp_webhook"]` + lifespan extras. RLS policies follow `KB § PATTERNS/database-rls.md`. Tests use the three-layer discipline.
3. **Product owns: domain + flows + prompts + UI. Seed owns: plumbing.** The product writes the system prompt, defines the intent registry, names the entities (Condominium, Property, Service, Appointment, AppointmentRequest, Conversation), and supplies the `audit_writer = default_audit_writer(db)` to the chatbot framework. The seed provides the connector, the conversation buffer, the worker shell, the LLM dispatcher, the tool-audit model, the scheduling engine.
4. **MCP-first for the product's tools.** Every tool the bot's LLM may call (lookup_property, propose_appointment, confirm_appointment, list_my_appointments, etc.) lands as an MCP tool first under `platform.business.<service>.<action>` (per `projects/mcp-server-expansion/`). The bot consumes them via the in-process import path (per the dual-callable pattern); future agents (Claude Code, Vista CRM agents) consume the same tools via MCP transport.
5. **AST-first for code edits**, per the user's parallel mandate (lifting from automations methodology). When AST tooling is set, all product code edits use it.
6. **Frontend optional in v1.** The bot's primary interface is WhatsApp (no UI required). Reference-data administration (users / condos / properties / services / crew) gets a frontend in a later phase if the user wants — sibling's `admin-surface` plan informs scope. Decided in §7.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** N/A — this IS a product. The contracts the product *consumes* (chatbot framework, scheduling engine, tool audit, MCP business tools) are uniform across products by design.
2. **Is the data source product-specific?** YES — this product owns its `condominiums`, `properties`, `services`, `media_crew`, `appointments`, `appointment_requests`, `conversation_messages` tables.
3. **Is the placement product-specific?** YES — under `products/<slug>/`.
4. **Is the visibility / permission rule the same?** Per-product RLS — agency staff see their agency's data; media-crew see their assignments; admins see all.
5. **Does the seam already exist in seed?** YES for the framework pieces (chatbot framework, scheduling engine, etc., once the absorption-batch seed projects land). NO for this product itself — it's new.
6. **Default-on or opt-in?** N/A — products are independent entities.

**Litmus — per-product code count this design requires:** [x] **A small section** — the product's wiring is product-specific (system prompt, intent registry, tool registry, RLS, factory call). The plumbing it consumes is in seed.

**Phase plan implications:** §6 phases work in `products/<slug>/`. **No phase walks through other products.** Reverse direction (this product consuming seed) is correct shape.

---

## 4. Scope

**In scope:**

- Phase 0 audit (slug confirmation, port allocation, RLS shape, frontend yes/no).
- Scaffold via `noctusai_scaffold_product(slug, ...)` MCP tool (Phase 1).
- Backend factory wiring with seed routers + chatbot framework + tool-audit + scheduling engine.
- Domain models: Condominium, Property, Service, MediaCrew, Appointment, AppointmentRequest, Conversation, ConversationMessage, ConversationSummary, ToolCallAudit (the last by lib import; products' migration adds the table).
- Alembic migrations matching the product's domain.
- Authorization (LID-aware WhatsApp inbound auth — sibling's `security-hardening` work folds in here).
- Intent extraction + system prompt (pt-BR for first-pass; localization deferred — see §7).
- Tool registry (lookup_property, propose_appointment, confirm_appointment, cancel_appointment, reschedule_appointment).
- Calendar wiring (uses absorbed `noctusai_lib.integrations.google_calendar`).
- Routing wiring (uses absorbed `noctusai_lib.integrations.google_maps`).
- Cancellation + reschedule conversation flows (folded from sibling's `cancellation-rescheduling`).
- WAHA session configuration + webhook routing.
- Audit-row persistence wired (uses absorbed `noctusai_lib.domain.ai.tool_audit`).
- Production-readiness checklist (folded from sibling's `production-hardening`: retries, structured logs, deployment target, backups, health, metrics — applied to the product's services).
- Security hardening (folded from sibling's `security-hardening`: rate limits, prompt-injection test suite, output sanitization, anomaly detection — applied at the product's webhook + LLM dispatcher).
- Idempotency on WAHA `provider_message_id` + Calendar `requestId` (folded from sibling's `idempotency-keys`).
- `README.md` + `MASTER-PROMPT.md` from day one.
- Three-layer test coverage.

**Out of scope (for now — with reason):**

- Frontend admin UI (sibling's `admin-surface` plan) — deferred to its own phase or follow-up project; primary interface is WhatsApp. **OPEN QUESTION**.
- Bulk CSV import for reference data (sibling's `bulk-import` idea) — deferred until admin UI exists.
- Multi-crew load balancing rules (sibling's `crew-assignment-rules` idea) — sibling has only one crew; revisit when a second exists.
- End-customer lead categorization (sibling's `end-customer-lead-categorization` idea) — bot is staff-facing v1; end-customer expansion is a separate product or phase.
- Localization (sibling's `localization` idea) — pt-BR only in v1.
- State machine for `appointment_request` (sibling's `state-machine-for-requests` idea) — refinement post-MVP.
- GPT confidence thresholds (sibling's `gpt-confidence-thresholds` idea) — refinement post-MVP.
- Provider-payload audit (raw WAHA / OpenAI / Calendar payloads) — refinement; pairs with data-retention.
- Operational dashboards — depends on platform-wide metrics sink; deferred to its own follow-up.

---

## 5. Architecture / Data Model

### 5.1 The there → here map (sibling product semantics → this product's implementation)

The sibling code is **not lifted**. Its semantics are. This map records what the new product's code must implement, and where each capability lives in the absorbed seed vs. in this product.

| Sibling capability (semantic) | Where it lives HERE | Notes |
|---|---|---|
| WAHA inbound webhook + signature verification + idempotency | `noctusai_lib.integrations.whatsapp.create_whatsapp_webhook_router(...)` mounted via `standard_routers=[..., "whatsapp_webhook"]` | Seed feature; product just wires it. |
| Conversation buffer + debounce in Redis | `noctusai_lib.domain.conversation.buffer` configured via `configure_conversation_module(...)` | Seed; product wires. |
| Worker that processes due conversations | `noctusai_lib.domain.conversation.worker.ConversationWorker.run_forever()` started in lifespan | Seed; product wires. |
| OpenAI tool-loop chat | `noctusai_lib.domain.conversation.llm_dispatcher` configured with this product's system prompt + tool registry | Seed; product configures. |
| Tool-call audit | `noctusai_lib.domain.ai.tool_audit.default_audit_writer(db)` wired into dispatcher | Seed; product wires. |
| Scheduling rules engine (working windows, lunch, travel-buffer, same-condo duration, candidate generation) | `noctusai_lib.domain.scheduling.SchedulingEngine` configured with this product's `SchedulingRules` (real-estate vocabulary) | Seed; product configures. |
| Google Calendar adapter (OAuth + service-account + Fake) | `noctusai_lib.integrations.google_calendar` configured via `configure_calendar_module(...)` | Seed; product wires. |
| Google Maps routing (Routes / Distance Matrix + Static fallback) | `noctusai_lib.integrations.google_maps` configured via `configure_maps_module(...)` | Seed; product wires. |
| User authorization (phone-number lookup, role check) | `products/<slug>/backend/app/services/authorization.py` — uses platform's role model + LID-aware lookup pattern | Product. LID-awareness folds in from sibling's `security-hardening`. |
| Domain entities: Condominium, Property, Service, MediaCrew, Appointment, AppointmentRequest, Conversation, ConversationMessage, ConversationSummary | `products/<slug>/backend/app/models/` + Alembic migrations | Product owns the schema; replicated FROM SCRATCH on noctusai patterns (Pydantic v2 + SQLAlchemy 2.0 + RLS). |
| Intent extraction (schedule / cancel / reschedule + reference data lookup) | `products/<slug>/backend/app/services/intent_extraction.py` | Product. |
| Reference-data tools (lookup_property, propose_appointment, confirm_appointment, cancel_appointment, reschedule_appointment) | MCP tools under `platform.business.<service>.<action>` per `projects/mcp-server-expansion/` Phase 5 | Tools land in MCP; product imports + dispatches in-process. |
| System prompt (Portuguese pt-BR, in-character as scheduling bot) | `products/<slug>/backend/app/prompts/scheduling_bot.md` | Product owns the prose. |
| Conversation summary on idle | `noctusai_lib.domain.conversation.summary` (opt-in flag) — product enables | Seed; product opts in. |
| WhatsApp pushName auto-update on inbound | Implemented in product's webhook handler hook (passed to seed router via DI) | Bot-specific behavior; seed provides hook. |
| Rejection-reply persistence on unauthorized inbound | Same as above — product hook | Bot-specific behavior; seed provides hook. |

### 5.2 Product layout (target)

```
products/<slug>/                    ← target slug pending §7 Q1 confirmation
├── README.md                       ← human-facing: what the product is
├── MASTER-PROMPT.md                ← agent-facing: how to build features here
├── backend/
│   ├── app/
│   │   ├── main.py                 ← create_product_app(...) call
│   │   ├── config.py               ← ProductSettings (extends BaseAppSettings)
│   │   ├── models/                 ← SQLAlchemy entities
│   │   ├── schemas/                ← Pydantic DTOs
│   │   ├── routers/                ← product-specific routers (admin endpoints if any)
│   │   ├── services/
│   │   │   ├── authorization.py
│   │   │   ├── intent_extraction.py
│   │   │   ├── scheduling.py        ← thin wrapper that builds SchedulingRules + calls noctusai_lib.domain.scheduling
│   │   │   ├── tool_registry.py     ← MCP business-tools registered for this bot
│   │   │   └── ...
│   │   ├── prompts/                 ← system prompt(s) + few-shot examples
│   │   └── lifespan.py              ← starts the conversation worker
│   ├── migrations/                  ← Alembic
│   ├── tests/                       ← three-layer
│   └── pyproject.toml
└── frontend/                        ← optional v1 (admin UI), see §7 Q3
    └── (standard noctusai vite + react + tanstack stack if scoped in)
```

### 5.3 Configuration

Single root `.env` per `KB § PATTERNS/environment.md`. New keys:

```bash
# Product-side
IMOBI_SCHEDULING_TIMEZONE=America/Sao_Paulo
IMOBI_SCHEDULING_MORNING_START=09:00
# ... (rest of scheduling rules)

# Seed-feature wiring (already exist if other products use them; new for this product)
WAHA_BASE_URL=...
WAHA_API_KEY=...
WAHA_SESSION=imobi_scheduling   # one session per bot
WAHA_WEBHOOK_HMAC_SECRET=...
CONVERSATION_MEMORY_TTL_SECONDS=3600
MESSAGE_DEBOUNCE_SECONDS=8
# ... etc
GOOGLE_CALENDAR_OAUTH_CLIENT_ID=...
GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET=...
GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE=...
GOOGLE_MAPS_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

---

## 6. Implementation phases

**Massive work. ~14 phases. Phase-by-phase by default.**

### Phase 0 — Audit + decisions

- [ ] Confirm target product slug (Q1).
- [ ] Confirm port allocation (Q2 — pick a number under `KB § 05-INFRASTRUCTURE.md` rules).
- [ ] Decide frontend yes/no (Q3).
- [ ] Decide RLS shape (single-agency vs. multi-tenant).
- [ ] Confirm dependency order: which absorption-batch seed projects must complete before which phase here. **Recommended:** Phase 1 (scaffold) waits on **none**. Phases 5+ depend on the seed projects landing.
- [ ] Read sibling repo end-to-end for any product-domain detail not yet captured (validation evidence). After this read, sibling repo is **read-only reference for the duration of this project**; no leftovers post-completion.

### Phase 1 — Scaffold the product

- [ ] Run `python mcp/noctusai/cli.py noctusai_scaffold_product --slug=<slug>` (or equivalent).
- [ ] Verify `products/<slug>/{backend, frontend?, README.md, MASTER-PROMPT.md}` exists and is shape-compliant per `KB § GUIDES/new-product.md`.
- [ ] Initial commit boundary.

### Phase 2 — Backend foundation

- [ ] `products/<slug>/backend/app/main.py` calls `create_product_app(...)` with seed defaults.
- [ ] `products/<slug>/backend/app/config.py` extends `BaseAppSettings`.
- [ ] `pyproject.toml` declares deps on `noctusai_lib` (editable install).
- [ ] First Alembic migration (empty baseline).
- [ ] Verify `pytest products/<slug>/backend/` smoke tests green.

### Phase 3 — Domain models + migrations

- [ ] Create models for Condominium, Property, Service, MediaCrew, Appointment, AppointmentRequest, Conversation, ConversationMessage, ConversationSummary.
- [ ] Generate Alembic migration for the schema.
- [ ] RLS policies per `KB § PATTERNS/database-rls.md` (subquery `auth.uid()`, `search_path`, etc.).
- [ ] Apply migration via Supabase MCP (`mcp__claude_ai_Supabase__apply_migration`) AND commit the migration file (`KB § PATTERNS/database-rls.md` mirroring rule).
- [ ] Tests on model invariants + RLS policies.

### Phase 4 — Authorization

- [ ] `products/<slug>/backend/app/services/authorization.py` — phone lookup, LID-aware (sibling's `security-hardening` LID work folds in here).
- [ ] Tests covering phone match, LID match, unauthorized rejection.

### Phase 5 — Wire seed: WhatsApp connector

- [ ] In `lifespan.py` and `main.py`: `configure_whatsapp_module(...)`; mount `whatsapp_webhook` standard router.
- [ ] Provide product hooks (pushName auto-update; rejection-reply persistence) via DI to the seed router.
- [ ] WAHA session configured.
- [ ] Webhook signature secret in `.env`.
- [ ] Manual smoke test end-to-end (send a WhatsApp message; verify webhook persists).

### Phase 6 — Wire seed: chatbot framework + tool-audit

- [ ] `configure_conversation_module(...)` with `audit_writer = default_audit_writer(db)`.
- [ ] Lifespan starts `ConversationWorker.run_forever()` as a background task.
- [ ] System prompt at `app/prompts/scheduling_bot.md` (port pt-BR prose from sibling, adapted for our seam).
- [ ] Initial tool registry: `lookup_property`, `propose_appointment`, `confirm_appointment` (more in Phase 9).
- [ ] Tests (mocked OpenAI client + audit writer).

### Phase 7 — Wire seed: scheduling engine

- [ ] `app/services/scheduling.py` builds `SchedulingRules` with real-estate vocabulary mapping (location_id = condominium_id; assignee = media crew; transition_buffer = travel_buffer).
- [ ] Custom `Conflict` for property-availability + crew-availability.
- [ ] Optional: custom scorer using Maps adapter for travel distance.
- [ ] Tests verifying the bot's scheduling cases (lunch blocking, same-condo duration, travel-buffer enforcement) match sibling's behavior under our wiring.

### Phase 8 — Wire seed: Google Calendar + Google Maps

- [ ] `configure_calendar_module(...)` with OAuth refresh-token persistence (folded from sibling's `google-oauth-activation` runbook).
- [ ] `configure_maps_module(...)`.
- [ ] Calendar `requestId` idempotency (folded from sibling's `idempotency-keys`).
- [ ] Tests using `FakeCalendarAdapter` + `StaticRoutingAdapter`.

### Phase 9 — Cancellation + reschedule flows

- [ ] Intent variants for cancel + reschedule (folded from sibling's `cancellation-rescheduling`).
- [ ] Tools: `cancel_appointment`, `reschedule_appointment`.
- [ ] Conversation flow: confirmation step before write tools fire.
- [ ] Tests.

### Phase 10 — Production hardening

- [ ] Retries on transient failures (WAHA send, Calendar create) with exponential backoff.
- [ ] Structured logs via `noctusai_lib.logging_config.configure_logging`.
- [ ] Deployment target documented (Compose / k8s — decided in Phase 0).
- [ ] DB backup procedure documented.
- [ ] Health-check endpoint (covered by `standard_routers=["health"]`).
- [ ] Metrics sink TBD — surfaces `KB § PATTERNS/chatbot-operational-readiness.md` (NEW pattern doc). Folded from sibling's `production-hardening` + `operational-dashboards`.

### Phase 11 — Security hardening

- [ ] Rate-limit per-conversation inbound (existing `noctusai_lib.api.rate_limit` if available; else add).
- [ ] Prompt-injection test suite (`tests/security/test_prompt_injection.py`) — sibling's planned tests inspire shape.
- [ ] Output sanitization for any PII before LLM-tool dispatch returns to the conversation.
- [ ] Anomaly detection (TBD — basic threshold first; ML later).
- [ ] Surfaces `KB § PATTERNS/llm-bot-security.md` (NEW pattern doc). Folded from sibling's `security-hardening`.

### Phase 12 — README + MASTER-PROMPT + KB

- [ ] `README.md` (human-facing).
- [ ] `MASTER-PROMPT.md` (agent-facing).
- [ ] Update `KB § 02-LANDSCAPE.md` with this product's row.
- [ ] Update `KB § INDEX.md` if new pattern docs landed (`chatbot-operational-readiness.md`, `llm-bot-security.md`).
- [ ] `CLAUDE.md §3 Map` per-product pointer.
- [ ] Three-way sync (KB ↔ CLAUDE.md ↔ memory).

### Phase 13 — Frontend (CONDITIONAL — see §7 Q3)

- [ ] If yes: scaffold via product seed; admin UI for users / condos / properties / services / media crew (sibling's `admin-surface` semantics, our patterns).
- [ ] If no: skip; document rationale in §11.

### Phase 14 — Final verification + go-live

- [ ] All three test layers green.
- [ ] `bash scripts/verify-kb-sync.sh` green.
- [ ] `python mcp/noctusai/cli.py --review` clean (or triaged 3-way).
- [ ] Manual end-to-end smoke against staging WAHA + sandbox Calendar.
- [ ] Confirm sibling repo deletion is now safe (no functional loss).

---

## 7. Open questions

1. **Product slug?** Proposed: `imobi-scheduling`. Alternatives: `imobi-media-scheduling`, `realty-content-scheduling`. Decided before Phase 1 (it's the most-painful-to-rename decision in the whole project). User decides.
2. **Port allocation?** Pick from `KB § 05-INFRASTRUCTURE.md` available pool. Decided before Phase 2.
3. **Frontend in v1?** Recommendation: **defer** — primary interface is WhatsApp; admin UI can land in a follow-up project once the bot is in steady state. Decided before Phase 13.
4. **Single-agency or multi-tenant?** Recommendation: **single-agency v1** (mirrors sibling); multi-tenant is a refactor when a second agency arrives. Decided before Phase 3 (RLS shape).
5. **Standalone or paired with `erp-imobiliario`?** Recommendation: **standalone product** but shares conventions with erp-imobiliario; cross-product data (e.g., property catalog) is a future integration concern. Decided before Phase 0 closes.
6. **Localization in v1 (pt-BR + en)?** Recommendation: **pt-BR only**; localization framework is a future seed concern. Decided in Phase 6.
7. **LGPD posture?** Run the five questions (`KB § PATTERNS/lgpd.md`) over conversation message storage + tool audit rows. Recommendation: conversation messages are PII (phone, name, possibly location); tool audit rows hold the same; document basis + retention in Phase 12 KB doc. Apply `noctusai_lgpd_flag(...)` if uncertain.
8. **Bot's WhatsApp number?** Operational decision; needs WAHA session provisioning. Decided before Phase 5.

---

## 8. Dependencies & blockers

- **`projects/whatsapp-seed-absorption/`** — Phases 5–8 depend on its lib being import-able. Blocker for Phase 5.
- **`projects/llm-tool-call-audit/`** — Phase 6 depends on `default_audit_writer` existing. Blocker for Phase 6.
- **`projects/scheduling-engine-seed/`** — Phase 7 depends on `noctusai_lib.domain.scheduling` existing. Blocker for Phase 7.
- **`projects/mcp-server-expansion/`** — Phase 5 (sibling tool absorption into our MCP) provides the business-logic tools this product registers. Blocker for full Phase 6 (initial tool registry can be inline; MCP-tool form is the second iteration). 
- **WAHA infrastructure** — needs a session provisioned before Phase 5 manual smoke.
- **Google Cloud OAuth + Maps API keys** — operational; needed by Phase 8.

**Recommended execution order:** Phases 0–4 can run in parallel with the four seed projects landing; Phases 5–9 wait on seed-project dependencies; Phases 10–14 close out.

---

## 9. Success criteria

- [ ] `products/<slug>/` exists, scaffold-compliant per `KB § GUIDES/new-product.md`.
- [ ] All three test layers green: `pytest products/<slug>/backend/`, `npm test products/<slug>/frontend/` (if frontend in v1), end-to-end smoke.
- [ ] Bot answers a real WhatsApp inbound, schedules a real Google Calendar event, persists audit + memory + summary rows.
- [ ] Sibling repo can be deleted with no functional regression.
- [ ] `KB § 02-LANDSCAPE.md` includes this product.
- [ ] `bash scripts/verify-kb-sync.sh` green.

---

## 10. How to use this plan

```bash
# Sibling reference (read-only, for the project's lifetime)
ls ~/Documents/repository/NoctusAI/whatsapp-google-scheduling/
# After this project closes, the user will delete the above. No remaining references.

# Product scaffold (Phase 1)
python mcp/noctusai/cli.py noctusai_scaffold_product --slug=<confirmed-slug>

# Per-phase verification
pytest products/<slug>/backend/
bash scripts/verify-kb-sync.sh
python mcp/noctusai/cli.py --review
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial project drafted; user confirmed bot becomes a noc product implemented fresh on our patterns; consumes the absorption-batch seed projects; sibling-folder deletion safe-after-completion is part of success criteria. | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) WILL BE DELETED by the user once the absorption batch (this project + the four seed projects) is complete. This project's success requires:

- **No sibling-path references survive** in product code, KB docs, MASTER-PROMPT, or README. Sibling refs in this PROJECT.md are execution-scoped — the project folder gets deleted on close per apply-inline-then-delete.
- **No symlinks, no editable installs, no path deps** to the sibling. The product's `pyproject.toml` declares deps on `noctusai_lib` (in our seed) only.
- **Tests stand alone.** Any test fixture inspired by sibling tests is rewritten to the product's data shape.
- **Phase 14's go-live verification includes a sibling-deletion safety check.** The project does not close until that check passes.
