# imobi-scheduling-bot-creation — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update §11.
>
> **Write for a zero-context reader.** Inline context in §1, quote the user in §2, name files with paths in §5, pair every §7 Open Question with an evidence-backed recommendation, make §10 commands copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-11
- **Status:** ⏳ **EXECUTING** — Phases 0-9 ✅ complete (audit + scaffold + foundation + domain models + auth + WhatsApp connector + chatbot framework + scheduling engine + Calendar/Maps + cancel/reschedule flows). 308/308 tests green. Phases 10-14 (production-hardening / security / docs / final verify) pending.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § GUIDES/new-product.md` (canonical product creation guide), `KB § 02-LANDSCAPE.md` (existing products + ports), `projects/whatsapp-seed-absorption/PROJECT.md` (this product is its **first consumer**), `projects/llm-tool-call-audit/PROJECT.md` (this product is its **first consumer**), `projects/scheduling-engine-seed/PROJECT.md` (this product is its **first consumer**), `projects/mcp-server-expansion/PROJECT.md` (this product is the **first MCP business-logic-tool client**), templates at `templates/PROJECT-TEMPLATE.md` + `templates/product-seed/`.
- **Project slug:** `imobi-scheduling-bot-creation` — cross-cutting "not-yet-a-product" project per `KB § PATTERNS/project-execution.md §1` (the work itself creates the product; lives at root `projects/<slug>/` until the product exists, then promotes to `products/<product-slug>/projects/`).
- **Target product slug:** `imobi-scheduling` ✅ confirmed 2026-05-10 (orchestrator-stamped default).

---

## 1. Context & Purpose

The user has a tested, working WhatsApp scheduling bot at sibling repo `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`. It schedules real-estate content production appointments (media-crew showings of properties for content production: photos, video, drone) routed through Google Calendar, with conversation memory, debounce, idempotency, OAuth/service-account/Fake calendar adapters, Maps routing, audit trail, and unit-tested scheduling rules. End-to-end working MVP.

The user wants this **rebuilt as a NoctusAI product on our own patterns**, freshly implemented — not lifted as a code-port, but reimplemented consuming the seed features the absorption batch is producing. *"We're gonna create this as a noc product, got it? That's what i meant by there->here plan, so we implement the product on own code pattern as it should be, right from fresh start."*

This product is the **first consumer** of three seed efforts landing in parallel:
1. `projects/whatsapp-seed-absorption/` → `noctusai_lib.integrations.whatsapp` + `noctusai_lib.domain.chatbot`.
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
- Scaffold via `noctus.dev.scaffold_product(slug, ...)` MCP tool (Phase 1).
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
| Conversation buffer + debounce in Redis | `noctusai_lib.domain.chatbot.buffer` configured via `configure_conversation_module(...)` | Seed; product wires. |
| Worker that processes due conversations | `noctusai_lib.domain.chatbot.worker.ConversationWorker.run_forever()` started in lifespan | Seed; product wires. |
| OpenAI tool-loop chat | `noctusai_lib.domain.chatbot.llm_dispatcher` configured with this product's system prompt + tool registry | Seed; product configures. |
| Tool-call audit | `noctusai_lib.domain.ai.tool_audit.default_audit_writer(db)` wired into dispatcher | Seed; product wires. |
| Scheduling rules engine (working windows, lunch, travel-buffer, same-condo duration, candidate generation) | `noctusai_lib.domain.scheduling.SchedulingEngine` configured with this product's `SchedulingRules` (real-estate vocabulary) | Seed; product configures. |
| Google Calendar adapter (OAuth + service-account + Fake) | `noctusai_lib.integrations.google_calendar` configured via `configure_calendar_module(...)` | Seed; product wires. |
| Google Maps routing (Routes / Distance Matrix + Static fallback) | `noctusai_lib.integrations.google_maps` configured via `configure_maps_module(...)` | Seed; product wires. |
| User authorization (phone-number lookup, role check) | `products/<slug>/backend/app/services/authorization.py` — uses platform's role model + LID-aware lookup pattern | Product. LID-awareness folds in from sibling's `security-hardening`. |
| Domain entities: Condominium, Property, Service, MediaCrew, Appointment, AppointmentRequest, Conversation, ConversationMessage, ConversationSummary | `products/<slug>/backend/app/models/` + Alembic migrations | Product owns the schema; replicated FROM SCRATCH on noctusai patterns (Pydantic v2 + SQLAlchemy 2.0 + RLS). |
| Intent extraction (schedule / cancel / reschedule + reference data lookup) | `products/<slug>/backend/app/services/intent_extraction.py` | Product. |
| Reference-data tools (lookup_property, propose_appointment, confirm_appointment, cancel_appointment, reschedule_appointment) | MCP tools under `platform.business.<service>.<action>` per `projects/mcp-server-expansion/` Phase 5 | Tools land in MCP; product imports + dispatches in-process. |
| System prompt (Portuguese pt-BR, in-character as scheduling bot) | `products/<slug>/backend/app/prompts/scheduling_bot.md` | Product owns the prose. |
| Conversation summary on idle | `noctusai_lib.domain.chatbot.summary` (opt-in flag) — product enables | Seed; product opts in. |
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

### Phase 0 — Audit + decisions ✅

- [x] Confirm target product slug (Q1). ✅ **`imobi-scheduling`** (orchestrator-stamped 2026-05-10).
- [x] Confirm port allocation (Q2 — pick a number under `KB § 05-INFRASTRUCTURE.md` rules). ✅ **backend 8011 / frontend 8160** (engineer pick via `noctus.dev.available_ports`; rationale in §11).
- [x] Decide frontend yes/no (Q3). ✅ **DEFER frontend** (WhatsApp-only v1; admin UI in a follow-up project) — orchestrator-stamped 2026-05-10. Scaffold ships a placeholder frontend by default (always-on at tool level); accepted-with-rationale, see §11.
- [x] Decide RLS shape (single-agency vs. multi-tenant). ✅ **single-agency v1** (multi-tenant is a refactor when a second agency arrives) — orchestrator-stamped 2026-05-10.
- [x] Confirm dependency order: Phase 1 (scaffold) waits on **none**. Phases 5+ depend on the seed projects landing — **all 4 substrate seed projects shipped** (whatsapp + chatbot + llm-tool-audit + scheduling-engine + Calendar/Maps). Phases 5-8 are unblocked. ✅ orchestrator-stamped 2026-05-10.
- [x] Read sibling repo `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/` end-to-end for any product-domain detail not yet captured (validation evidence). ✅ Audit notes in `findings.md` §4 (sibling-repo domain detail). Sibling repo is now **read-only reference for the duration of this project**; no leftovers post-completion.

**Improvements:** none identified — Phase 0 is design-only decision phase; no code touched. All orchestrator-stamped defaults accepted by engineer audit.

### Phase 1 — Scaffold the product ✅

- [x] Run `noctus.dev.scaffold_product` MCP tool (name=Imobi Scheduling, slug=imobi-scheduling, schema=imobi_scheduling, backend=8011, frontend=8160, color=#10b981, icon=CalendarClock). Emitted: 58 files at `products/imobi-scheduling/`, seed-row migration at `products/core/backend/migrations/028_seed_imobi_scheduling_product.sql`, registration in `start.sh` + root `docker-compose.yml`.
- [x] Verify `products/imobi-scheduling/{backend, frontend, README.md, MASTER-PROMPT.md, docker-compose.yml}` exists and is shape-compliant per `KB § GUIDES/new-product.md`. Backend has `app/{main,config,database,dependencies,middleware,logging_config,rate_limit,responses}.py` + `routers/` + `schemas/` + `services/` + `migrations/` + `tests/` (41/41 green: health=14, example_router=5, webhook_router=5, team_router=14, e2e=3).
- [x] Smoke test green: `pytest tests/ -q` → 41 passed.
- [x] Initial commit boundary (this engineer commit). Phases 2+ build on this.

**Improvements:**
- **P0 — MCP scaffold tool bypasses worktree isolation.** `noctus.dev.scaffold_product` wrote to canonical noc root (main worktree) instead of the engineer's worktree. Engineer worked around via `cp -r` + hand-mirror of `start.sh` / root `docker-compose.yml`. Follow-up project filed (`projects/mcp-worktree-path-resolution/`).
- **N=2 frontend-deferred recurrence** (imobi + youtube-crawler). Scaffold tool has no `--backend-only` opt-out — future MCP enhancement: `backend_only=True` flag.
- **LLM-rewrite returned None** at scaffold for README + MASTER-PROMPT. Product ships seed-template prose. Phase 12 prose authoring handles re-run.
- **Open question (decide before close)**: `media-scheduling/` (prior 2026-05-04 code-port) vs `imobi-scheduling/` (fresh implementation). Architect-decision needed.

### Phase 2 — Backend foundation

- [ ] `products/<slug>/backend/app/main.py` calls `create_product_app(...)` with seed defaults.
- [ ] `products/<slug>/backend/app/config.py` extends `BaseAppSettings`.
- [ ] `pyproject.toml` declares deps on `noctusai_lib` (editable install).
- [ ] First Alembic migration (empty baseline).
- [ ] Verify `pytest products/<slug>/backend/` smoke tests green.

### Phase 3 — Domain models + migrations ✅

- [x] Create Pydantic models for Condominium, Property, Service, MediaCrew (users w/ role), Appointment, AppointmentRequest, ConversationMessage, ConversationSummary + Engineer-E audit expansion (crew_skill, oauth_credential, pending_chat_identity, route + supporting users / appointment_request_services / route_groups / tool_call_audits). 15 domain tables in total.
- [x] Append tables to single 001 migration (`products/imobi-scheduling/backend/migrations/001_imobi_scheduling.sql`). Topological order: users → condominiums → properties → services → crew_skills → appointment_requests → appointment_request_services → route_groups → appointments → conversation_messages → conversation_summaries → pending_chat_identities → oauth_credentials → routes → tool_call_audits.
- [x] RLS policies single-agency v1 (Phase 0 Q4): every org-bound table SELECT/INSERT/UPDATE/DELETE scopes via `org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid`; UPDATE policies pin `WITH CHECK` (Engineer-D ERP lesson); append-only tables (`conversation_messages`, `tool_call_audits`) explicitly omit UPDATE policies; `search_path` pinned via prelude.
- [x] Applied migration via `mcp__claude_ai_Supabase__apply_migration` → `001_imobi_scheduling` + follow-up `001_imobi_scheduling_missing_fk_indexes` (closes the 4 unindexed_foreign_keys advisor INFOs surfaced post-apply). All 17 tables (2 framework + 15 domain) live with RLS enabled. File mirrors live DB.
- [x] 125 structural tests added (89 migration parse + 36 schema validation). Full suite 166 green (was 41).

**Improvements:**
- **Indexed-FK advisor surfaced 4 missing indexes** — appointment_requests.condominium_id, appointments.condominium_id, appointments.route_group_id, pending_chat_identities.resolved_to_user_id. Applied INLINE during phase (file + DB both updated). No proposal needed.
- **Recurrence-watch:** every product migration with org-scoped tables emits ~17 `unused_index` advisor INFOs on first apply (no traffic yet). Filter these from review noise. Not a finding per-se but worth flagging if a future master-tree scans advisor output.
- **`pydantic` protected_namespaces conflict on `model_used`** — first time hitting it for a `model_` prefix on a domain field. Solved with `protected_namespaces=()` in ConfigDict (in-scope). If N=2 surfaces, consider a seed-side helper `model_config_with_release_namespaces()` factory.
- **`mcp__claude_ai_Supabase__get_advisors` output exceeds Anthropic-side token cap.** Reading from disk + jq-style filter is the workaround. Surface candidate: per-product or per-schema filter at the MCP layer (cheap fix — proxy in noctus MCP server that calls Supabase MCP + projects to the requested schema). Logging to findings.md §5 for cross-project lift.

### Phase 4 — Authorization ✅

- [x] `products/imobi-scheduling/backend/app/services/authorization.py` — phone lookup, LID-aware (sibling's `security-hardening` LID work folds in here). Three resolution paths: (1) `users.linked_identity = chat_id` for known LIDs; (2) `users.phone_number = normalize(from_phone)` fallback; (3) opportunistic LID capture when path 2 matches + chat_id is a previously-unseen LID. `authorize_inbound(...)` returns `AuthorizationResult` value object — `authorized: bool`, `user_id: UUID | None`, `lid: str | None`, `role: str | None`. Companion `park_pending_lid(...)` upserts a `pending_chat_identities` row for deferred-auth (admin resolves later). Service is Supabase-client based (matches the seed's `example_service.py` pattern); uses `client.schema("imobi_scheduling")` bound once at construction so callers can observe writes consistently.
- [x] Tests covering phone match, LID match, unauthorized rejection, opportunistic LID capture, pending-LID parking, helpers (`normalize_phone_number`, `looks_like_lid`), and `AuthorizationResult` shape. 23 new tests at `tests/services/test_authorization.py`. Service-layer (no HTTP) → status-code-assertion rule does not apply.
- [x] `pytest products/imobi-scheduling/backend/ -q` → **189 passed** (was 166 baseline + 23 new).
- [x] `python mcp/noctusai/cli.py --review --product imobi-scheduling` → **0 issues**.

**Improvements:**
- **`phone_e164` vs `phone_number` brief drift (in-scope, accept).** Architect brief specified `phone_e164` column; Phase 3 shipped `phone_number` (matches the sibling repo + Supabase convention). Service implementation aligned with the shipped schema. No follow-up needed — column name is stable.
- **MockSupabaseClient select doesn't apply `.eq()` filters at execute time** (returns seeded `_data` as-is regardless of predicates). Tests that exercise multi-path lookup (path-1 LID vs path-2 phone) must use `set_sequential_responses` to control per-call returns, not `data=[seed_row]`. **Cataloged as a testing-pattern lesson** — pattern verified in `tests/services/test_authorization.py::TestOpportunisticLidCapture`. Filing as testing-pattern note for `KB § PATTERNS/testing.md` (cross-product lift candidate).
- **MockSupabaseClient `upsert(...)` doesn't track payloads** (`inserted_payloads` only fires for `insert`). Service switched from upsert (semantically idempotent) to insert + UNIQUE-constraint reliance + try/except for race tolerance. **Trade-off accepted in-scope**: real-DB behavior is equivalent (UNIQUE constraint enforces idempotency at DB layer); the catch+log on conflict surfaces (no silent error). Filing as candidate for `noctusai_lib.testing.mocks.MockRequestBuilder.upsert` enhancement — track payload mirror to `inserted_payloads` so production code can use upsert + tests observe the call. Cross-product lift candidate.
- **`schema()` returns a fresh MockSupabaseClient per call** — caching the scoped client at service construction (`self._scoped = client.schema(self.SCHEMA)`) saves per-request reconstruction AND gives tests a stable handle for assertion (`svc._scoped.table("users").updated_payloads`). Documented inline. Worth surfacing as a **convention for any service that uses a non-default schema** — the per-call construction surprises tests + adds runtime cost. Candidate for `KB § PATTERNS/backend.md` enrichment.
- **Worktree-isolation gap (recurrence, P0):** `python mcp/noctusai/cli.py` from the worktree fails (`No module named 'pydantic'` — worktree has no MCP venv). Resolved by using the main noc tree's venv directly: `/Users/.../noctusai/mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py`. Same shape as the `noctus.dev.scaffold_product` worktree-resolution gap surfaced in Phase 1 (`projects/mcp-worktree-path-resolution/`). N=2+ — the MCP toolkit consistently doesn't honor worktree filesystem isolation. Recurrence-rule fires: every worktree workflow that hits MCP CLI fails the same way. Flag for the existing `mcp-worktree-path-resolution` project.
- **AST-first not used for service authoring (greenfield carve-out).** Phase 4 created a new file from scratch — no rename/refactor of existing AST nodes was needed. AST-first applies primarily to code edits over existing files; for greenfield, `Write` is the appropriate tool. Documented for future engineers — this carve-out is per `KB § PATTERNS/ast.md` (the boundary rule is *if the file is parsed*; new files have no existing AST to preserve).

### Phase 5 — Wire seed: WhatsApp connector ✅

- [x] In `main.py`: consume `noctusai_lib.integrations.whatsapp` factories
      (`create_whatsapp_webhook_router` + `WhatsAppSettings`); mount via
      `routers=[..., whatsapp_router]` (option **b** — `whatsapp_webhook`
      is NOT in `noctusai_seed.routers._STANDARD_ROUTERS`, promotion
      deferred to N=2). No `lifespan.py` needed — `WhatsAppSettings`
      construction is import-time pure; no async bootstrap.
- [x] Product hooks via DI to the seed router (
      `app/routers/whatsapp_router.py::handle_inbound_whatsapp`):
      pushName auto-update onto `users.name`; rejection-reply persistence
      via `AuthorizationService.park_pending_lid` for LID inbounds; loud
      WARN-and-drop for non-LID unauthorized.
- [x] WAHA session configured (`waha_session_name` field, env
      `WAHA_SESSION_NAME=imobi_scheduling`).
- [x] Webhook signature secret in `.env.example`
      (`IMOBI_WHATSAPP_WEBHOOK_SECRET`). Backend `.env.example` is net-new
      for this product (no backend env-template pattern exists yet
      platform-wide — N=1 candidate for lift if a second product needs
      one).
- [x] Manual smoke test — **DEFERRED** (no WAHA in worktree). Mark
      ticked with destination = user smoke at next deploy drill
      (`./start.sh imobi-scheduling tunnel` once .env populated).

**Improvements:**
- **Rate-limit on WhatsApp webhook (Pin 4 of 5-pin contract)** — the seed
  router `create_whatsapp_webhook_router` does not expose a rate-limit
  seam. Mounting the seed router through a `slowapi.limiter` route-level
  dep would require either an outer wrapper route or a seam in the seed
  factory. Filed for a follow-up project against
  `noctusai_lib.integrations.whatsapp` (likely cross-cuts with the
  whatsapp_webhook standard-router-promotion work).
- **`whatsapp_webhook` not in `_STANDARD_ROUTERS`** — option (b) wired
  this product. Promote to standard-router shape when N=2 surfaces
  (e.g. mailing-bot, therapy-bot needing inbound WhatsApp). Three-step
  maintenance contract is documented at
  `seed/framework/backend/noctusai_seed/routers.py:242-248`.
- **Backend `.env.example` template gap** — no platform-wide
  `templates/product-seed/backend/.env.example`. This product ships one
  hand-rolled. If a second product needs the same, lift into the seed
  scaffolder (`scaffold_product` MCP tool) before shipping the third.
- **`MockSupabaseClient.schema()` returns fresh instances** — our test
  needed a `_StableScopedClient` wrapper to read back `inserted_payloads`
  / `updated_payloads` from a schema-scoped client at the router level.
  The `AuthorizationService` service-layer tests sidestep this by
  reaching into `svc._scoped`; router-level tests can't. If this
  recurs at N=2 (another router-level test reading back from scoped
  state), lift `_StableScopedClient` into `noctusai_lib.testing`.

### Phase 6 — Wire seed: chatbot framework + tool-audit ✅

- [x] `configure_conversation_module(...)` wired in `app/services/conversation.py`. **Seed gap surfaced**: the seed does NOT ship a `configure_conversation_module` factory — chatbot module is constructor-based (instantiate `ConversationBufferService` / `LLMDispatcher` / `ConversationWorker` directly). The product owns the wiring shape that the brief named. Same for `default_audit_writer(db)` — seed ships `make_audit_writer(db, table_class)` for **SQLAlchemy Session**; product is Supabase-client based. The product ships `app/services/tool_audit.py::make_supabase_audit_writer(...)` as the Supabase adapter; lift to seed at N=2. Both gaps tracked below.
- [x] Lifespan starts `ConversationWorker.run_forever()` as a background task. `app/lifespan.py::on_startup` → `app/services/conversation.py::start_worker()` → `schedule_coro(_run_worker_in_thread(worker), ...)` (per memory rule). Worker is **synchronous** (`time.sleep`), wrapped via `asyncio.to_thread(worker.run_forever)` to play nice with the asyncio event loop.
- [x] System prompt at `app/prompts/scheduling_bot.md` — pt-BR prose ported from sibling `whatsapp-google-scheduling/app/services/openai/conversation.py::SYSTEM_PROMPT`. Header / lifecycle prelude added; body stripped by the loader. **No copy-paste of sibling code** — only prose.
- [x] Initial tool registry: `lookup_property`, `propose_appointment`, `confirm_appointment` at `app/services/tool_registry.py`. OpenAI tool descriptors (`TOOL_DESCRIPTORS`) + stub implementations (`TOOL_IMPLEMENTATIONS`) + dispatch handler (`build_tool_handler()`). Phase 6 ships stubs that return `not_implemented` — Phase 7+ replaces with real DB / Calendar / scheduling-engine calls. Future MCP-tool exposure (project §3 principle 4) imports these same handlers; tracked below.
- [x] Tests — 38 new tests across 4 files (`tests/services/test_tool_registry.py` 13, `tests/services/test_tool_audit.py` 10, `tests/services/test_conversation.py` 11, `tests/lifespan/test_lifespan.py` 4). Mocked at the OpenAI SDK boundary + `schedule_coro` seam (no monkey-patching of our own code per memory rule). **237 passed** (was 199 baseline; +38). Keeper `--review --product imobi-scheduling` → 0 issues.

**Improvements:**
- **P0 — Seed gap: `configure_conversation_module` does not exist.** The brief named a factory the seed doesn't ship. Real surface is constructor-based (`ConversationBufferService(...)`, `LLMDispatcher(...)`, `ConversationWorker(...)`). Product-side `configure_conversation_module(...)` (in `app/services/conversation.py`) wraps the four constructors + the Supabase audit writer into a single call mirroring the brief's intent. **N=1 carve-out** — if a second product (therapy / mailing) needs the same wiring, lift to `noctusai_lib.domain.chatbot.configure_module(...)`. Filed as candidate for the chatbot-seed Fake+Real-adapter follow-up.
- **P0 — Seed gap: `default_audit_writer(db)` does not exist.** Seed ships `make_audit_writer(db, table_class)` which closes over **SQLAlchemy Session** + ORM class. This product is Supabase-client based. Built `app/services/tool_audit.py::make_supabase_audit_writer(admin_client, org_id, ...)` as the Supabase adapter. Signature also bridges `LLMDispatcher.AuditWriter` (`Callable[[ToolCall, ToolResult], None]`) → `AuditRecord` (`Callable[[AuditRecord], None]`) — the two seed surfaces use different shapes. Lift to seed at N=2 (next Supabase consumer of the tool-audit seam).
- **P1 — `ConversationWorker.run_forever()` is synchronous** (uses `time.sleep`). `schedule_coro(...)` per memory rule requires a coroutine, so we wrap via `asyncio.to_thread(worker.run_forever)`. The seed-side fix would be an async-native poll loop — but the worker's contract (`stop()` flag, `processor` callable) is sync-friendly today. Surface candidate for `noctusai_lib.domain.chatbot.worker` enhancement (async-native variant alongside the sync one). Not blocking — wrap pattern works.
- **P1 — Audit writer duration_ms always 0.** `LLMDispatcher`'s `AuditWriter` signature (`Callable[[ToolCall, ToolResult], None]`) does NOT surface a duration. Stamping 0 is loss-of-information at audit time. Seed-side fix: pass `duration_ms` (or `started_at`/`finished_at`) into the writer signature. Cross-cuts with the seed signature unification — the dispatcher writer expects 2-arg, the seed `make_audit_writer` writer expects 1-arg `AuditRecord`. Both surfaces are wrong-by-default for the real consumer. File a single follow-up against `noctusai_lib.domain.ai.tool_audit` once N=2 lands.
- **P2 — Tool registry → MCP-tool exposure deferred (project §3 design principle 4).** Tools `lookup_property` / `propose_appointment` / `confirm_appointment` are in-process today. Future: land under `platform.business.<service>.<action>` once `projects/mcp-server-expansion/` Phase 5 ships its business-tool mounting infrastructure. The current `TOOL_IMPLEMENTATIONS` dict is shape-compatible — the MCP exposure imports the same handlers. No duplication.
- **P2 — Tests added a global `_patch_conversation_module` autouse fixture in conftest.** Closes the "OpenAI key required at lifespan import" gap. The fixture patches at the SDK boundary (`OpenAI`) + the `schedule_coro` seam (closing the bare coroutine to suppress the "never awaited" warning). Pattern candidate for `KB § PATTERNS/testing.md § Conversation-framework conftest pattern` if a second product wires the same shape.
- **P2 — Worktree venv recurrence.** Per Phase 4 / 5 / 6 same-shape: `pytest` from worktree fails with `No module named 'noctusai_seed'` against the MCP venv. Resolution: use noc-root `venv` (`/Users/.../noctusai/venv/bin/python -m pytest tests/`). Same shape as `mcp-worktree-path-resolution` project. N=3+ now; flag for that project's scope.
- **P2 — System prompt strips markdown header at load time.** `build_system_prompt()` reads the .md file + slices off `#` / `>` lines until the first `Você` paragraph. A clean separator-line convention (e.g. `<!-- PROMPT-BODY-STARTS-HERE -->`) would be more robust. Filed as in-scope refinement candidate for Phase 12 prose authoring.

### Phase 7 — Wire seed: scheduling engine ✅

- [x] `app/services/scheduling.py` builds `SchedulingRules` with real-estate vocabulary mapping (location_id = condominium_id; assignee = media crew; transition_buffer = travel_buffer). Engineer-E defaults stamped: morning 09:00-12:00 / lunch 12:00-13:30 implicit / afternoon 13:30-16:30 / travel-buffer 10 min / standard 90 min / same-condo 60 min / slot grid 30 min. Lunch encoded as the IMPLICIT gap between the morning and afternoon `WorkingWindow`s — no `BlockedInterval` required; the engine cannot propose a slot the window doesn't cover.
- [x] **Custom `Conflict` for property-availability + crew-availability — DEFERRED to Phase 9 cancellation/reschedule scope.** Phase 7 ships `DefaultConflict` (overlap + transition-buffer gap on both sides), which already covers the imobi-MVP semantics: appointments at the same condominium block, appointments at other condominiums respect travel + buffer. The richer per-crew availability rule (crew_skills × per-crew BlockedInterval) lands when crew_skills wiring is needed (Phase 9 — cancellation + reschedule + per-crew filtering). Tracked in `**Improvements:**` below.
- [x] Custom scorer using Maps adapter for travel distance — **DEFERRED to Phase 8** (Google Maps wiring). Phase 7 ships `DefaultScorer` (sums travel from previous + to next) wired against `ZeroTravelLookup`. Phase 8 injects a `GoogleMapsTravelLookup` via the existing constructor seam (no code change here at Phase 8 — the `SchedulingService(travel_lookup=...)` parameter is in place).
- [x] **Real DB-backed implementations replace Phase 6 stubs:** `lookup_property` (properties + condominiums join via `SchedulingService.lookup_property`); `propose_appointment` (engine `candidate_slots` over `_fetch_existing_intervals` of `scheduled` appointments overlapping the date); `confirm_appointment` (final overlap re-check + insert into `appointments`). Calendar event creation deferred to Phase 8 — `google_calendar_event_id` argument plumbed through for Phase 8 to pass.
- [x] `app/services/tool_registry.py` extended with `build_tool_handler(scheduling_service=...)` — backward-compatible (no-arg fallback runs Phase 6 stubs, preserving the existing dispatch-loop tests). Live impls dispatched via `_LIVE_IMPLEMENTATIONS` map.
- [x] `app/services/conversation.py` + `app/lifespan.py` wire the `SchedulingService` into the `ConversationModule`; `_build_processor` passes the service to `build_tool_handler` so the worker's dispatch loop calls the live engine.
- [x] `app/config.py` Phase 7 knobs promoted from "forward-compat stubs" to LIVE — afternoon end changed `18:00` → `16:30` (matches brief / Engineer-E audit); new knobs: `travel_buffer_minutes` (10), `standard_duration_minutes` (90), `same_condo_duration_minutes` (60), `slot_grid_minutes` (30).
- [x] **24 new tests** (21 `tests/services/test_scheduling.py` + 4 `tests/services/test_tool_registry.py` for live dispatch). Engine math sanity (lunch unschedulable, same-condo 60-min shortcut, travel-buffer rejection); service-level DB orchestration (lookup, propose, confirm, conflict re-validation). Mocks at the Supabase boundary via `MockSupabaseClient.set_sequential_responses(...)`; no monkey-patching of our own code.
- [x] `pytest products/imobi-scheduling/backend/ -q` → **261 passed** (was 237 baseline; +24).
- [x] `python mcp/noctusai/cli.py --review --product imobi-scheduling` → **0 issues**.

**Improvements:**
- **P1 — `_CrewAvailabilityConflict` deferred to Phase 9.** Phase 7 ships only `DefaultConflict` (overlap + cross-location travel-buffer). A future per-crew rule would consume `BlockedInterval.assignee_id` (a hook the seed already supports) to filter slots by crew assignment. Land at Phase 9 (cancellation/reschedule already needs per-crew BlockedInterval surface). Not a seed gap — the seed Protocol supports it; we don't have a consumer site for it yet.
- **P1 — `GoogleMapsTravelLookup` is a stub today (`ZeroTravelLookup`).** Phase 8 (Google Maps wiring) will inject a real implementation via `SchedulingService(travel_lookup=...)`. Constructor seam already accepts it; no Phase 7 code change blocks Phase 8. The seed `TravelLookup` Protocol is one-method (`travel_minutes(origin, destination) → int`); the adapter will close over the maps client.
- **P1 — Calendar event creation is deferred to Phase 8.** `confirm_appointment` accepts `google_calendar_event_id` as a passthrough; Phase 8 will compose `calendar.create_event(...)` BEFORE calling into this method (the event ID becomes the durable cross-system handle). The DB-insert path ships here so Phase 8 only wires the Calendar adapter without re-touching the service.
- **P2 — `MockSupabaseClient` per-table sequential-response surface is verbose.** Setting up a propose-or-confirm test takes 3 sequential responses (`properties`, `condominiums`, `appointments`). Recurrence-watch: if a fourth call type (e.g. `crew_skills`) lands at Phase 9 we'll be at N=4 chained `set_sequential_responses` calls per test. Surface candidate for a `noctusai_lib.testing` helper — `setup_table_sequence(client, {"properties": [...], "condominiums": [...], ...})` — file at N=2 (next product / phase that triggers the same shape).
- **P2 — Appointment-overlap fetch uses inclusive bounds (`lt(start_at, day_end) AND gt(end_at, day_start)`).** This catches edge cases (an appointment crossing midnight). Defensible per the seed's date-window convention. Documented inline so a future reviewer doesn't `simplify` away the inclusive form.
- **P2 — `confirm_appointment` accepts `services: list[str]` but only logs them today.** The full `appointment_request_services` M2M wire-up lands at Phase 9 when the AppointmentRequest lifecycle ships. Surfaced loud in the docstring + a debug log so the slip doesn't go silent.
- **P3 — Worktree-venv recurrence N=4+.** Per Phases 4 / 5 / 6 / 7 same-shape: `pytest` from the worktree fails with `No module named 'noctusai_seed'` against the MCP venv. Resolution unchanged: use noc-root `/Users/.../noctusai/venv/bin/python -m pytest`. N=4+ for the engineer side; well past the N=3 formalize threshold. The existing `projects/mcp-worktree-path-resolution/` follow-up captures this — no new project needed.

### Phase 8 — Wire seed: Google Calendar + Google Maps ✅

- [x] `configure_calendar_module(...)` at `app/services/calendar.py` — builds the seed's `get_calendar_adapter(resolver, tenant_id=...)`. Defaults to `FakeCalendarAdapter` when no OAuth client config / service-account info is supplied; switches to `GoogleCalendarOAuthAdapter` or `GoogleCalendarServiceAccountAdapter` automatically via the seed factory based on what the `SupabaseCalendarCredentialResolver` returns. **OAuth refresh-token persistence**: resolver reads `imobi_scheduling.oauth_credentials` (org-scoped, RLS-bound); exposes `save_refreshed_token(...)` so callers can persist the refreshed access token + expiry back. (The seed's `GoogleCalendarOAuthAdapter._service()` already calls `google_creds.refresh(Request())` on expiry — Phase 8 closes the persistence half of that loop.)
- [x] `configure_maps_module(...)` at `app/services/maps.py` — builds the seed's `get_routing_adapter(api_key=...)`. Defaults to `StaticRoutingAdapter` when no key. **`GoogleMapsTravelLookup`** implements the engine's `TravelLookup` Protocol (1-method `travel_minutes(origin_id, destination_id) → int`); closes over a `location_id → Coordinates` map fetched at startup from `imobi_scheduling.condominiums` via `load_condominium_coords(admin, org_id)`. Same-id pair → 0; unknown id → configurable `default_minutes` (default 0 — `DefaultConflict.transition_buffer_minutes` absorbs the optimistic estimate).
- [x] Calendar `requestId` idempotency — `make_request_id(appointment_request_id, start_at_iso)` returns a SHA-256-truncated-32-char hex digest. Same logical inputs → same digest across retries. The `FakeCalendarAdapter` stores it as `x_request_id` on the event body so tests can verify stability. **Note**: today this is metadata only (the seed's `EventInput` docstring documents wire-level idempotency is deferred at the seed level — filing the seed-side follow-up below). Consumer-side enforcement via DB-pre-check is the current line of defense.
- [x] **`SchedulingService(..., calendar_event_factory=...)`** constructor seam — Phase 7 left Calendar event creation as a TODO; Phase 8 wires it via consumer injection. `confirm_appointment` calls the factory AFTER conflict re-validation but BEFORE the DB insert. **Failure to create the Calendar event aborts the booking** (no DB row written; ConfirmationResult(created=False, reason="calendar event creation failed: ...")). Compensation rationale: a failed Calendar create with a successful DB insert would mask the user-visible failure mode "I don't see it on my Calendar" — fail loud, don't desync.
- [x] **Lifespan wires both modules** at `app/lifespan.py::on_startup` BEFORE `configure_conversation_module(...)`. `app/services/conversation.py` reads them via `get_maps_module()` + `get_calendar_module()` and passes `travel_lookup=` + `calendar_event_factory=` into `SchedulingService(...)`. RuntimeError "not configured" caught at the conversation-module level → falls back to Phase 7 defaults (ZeroTravelLookup, no calendar) so unit tests bypassing lifespan still pass.
- [x] **31 new tests** (15 `test_calendar.py` + 13 `test_maps.py` + 3 `test_scheduling.py` for the factory wiring). Verify-the-seed-ships-it spot-checks via `FakeCalendarAdapter` + `StaticRoutingAdapter`; idempotency stability across retries; calendar-failure aborts DB insert; caller-supplied event_id skips factory. Mocks at the Supabase boundary via `MockSupabaseClient.set_sequential_responses(...)` + factory injection via constructor seam; no monkey-patching of our own code.
- [x] `pytest products/imobi-scheduling/backend/ -q` → **292 passed** (was 261 Phase 7 baseline; +31).
- [x] `python mcp/noctusai/cli.py --review --product imobi-scheduling` → **0 issues**.
- [x] **LGPD flagged**: `products/imobi-scheduling/backend/app/services/calendar.py:SupabaseCalendarCredentialResolver` — plaintext refresh-token storage; mitigation tracked in `LGPD-WARNINGS.md`.
- [x] Live OAuth + Maps API smoke — **DEFERRED** to user deploy drill (no real credentials in the worktree).

**Improvements:**
- **P0 — Seed gap: Calendar wire-level idempotency.** The seed's `EventInput.request_id` is metadata-only (the docstring at `seed/lib/backend/noctusai_lib/integrations/google_calendar/types.py` says wire-level idempotency is deferred to a future consumer-driven follow-up — `google-calendar-real-adapters` PROJECT.md §11 #3). The Fake adapter stores it as `x_request_id` (test-verifiable); the OAuth adapter does NOT translate it into Google's `body["id"]` + 409-swallow. Phase 8 implements the deterministic key + stamps it, but the actual wire-level guard requires seed-side work. **N=1 consumer.** File the seed real-adapter idempotency project when an N=2 consumer (therapy / mailing / daily-life calendar use) lands OR when imobi hits a real retry-storm in production.
- **P0 — Seed gap: OAuth refresh-token DB persistence is consumer-side.** The seed's `GoogleCalendarOAuthAdapter._service()` calls `google_creds.refresh(Request())` IN-MEMORY when the access token is expired, but the seed has no notion of "save the refreshed access_token back to the DB so the next process restart doesn't trigger another refresh." This product ships `SupabaseCalendarCredentialResolver.save_refreshed_token(...)` as the persistence half. **N=1 consumer** — at N=2 (next OAuth-backed product) lift to seed as a `CalendarTokenPersister` Protocol the adapter optionally calls post-refresh.
- **P1 — Refresh-token plaintext storage.** Migration 001 comments the `oauth_credentials.refresh_token` column as "SHOULD be encrypted at rest by the application before INSERT". Phase 8 does NOT yet implement the application-side encryption (the seed has no crypto envelope helper yet). LGPD-flagged via `noctus.dev.lgpd_flag` (see entry in `LGPD-WARNINGS.md`). Mitigation: short-term rely on Supabase's at-rest disk encryption + RLS; mid-term file `seed/lib crypto envelope helper for sensitive columns` project. The resolver is shaped so a future `encrypt_at_write` / `decrypt_at_read` pair plugs in transparently without changing the consumer code.
- **P1 — `load_condominium_coords` is a one-shot startup load.** No live refresh as condominium rows are added/edited. Acceptable in v1 (admin UI for condominiums lands later — Phase 13 frontend if approved). When the admin surface ships, this needs a `MapsModule.reload_condominium_coords()` method OR a buffer-side TTL cache. Surface candidate for `KB § PATTERNS/scheduling-seed.md` once a second product needs the same shape.
- **P1 — `_build_calendar_summary` / `_build_calendar_description` are hard-coded pt-BR.** Phase 12 (README + MASTER-PROMPT + KB) will introduce localization patterns; until then these strings live in `app/services/scheduling.py`. Surface candidate: lift to `app/prompts/calendar_templates.py` alongside the system prompt loader (Phase 12 will do it cleanly with i18n).
- **P2 — Calendar event service-account flow lifespan-wiring is incomplete.** `SupabaseCalendarCredentialResolver` accepts a `service_account_info` constructor arg but the lifespan path only wires OAuth client credentials from `settings.google_calendar_oauth_client_id/secret`. A future config flag (e.g. `GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE`) + a small JSON loader at startup is the minimal addition. Filed as a Phase 10 production-hardening item.
- **P2 — `routes` table caching is not consumed.** Migration 001 ships a `routes` table for caching origin/destination pairs from the Maps API; Phase 8 calls the seed adapter directly each time. Adding a check-cache-first wrapper inside `GoogleMapsTravelLookup` would reduce API spend on hot pairs (the bot frequently revisits the same condo pairs). Surface candidate when N=2 routing-cache consumer appears.
- **P2 — Worktree bootstrap script failed.** `bash scripts/bootstrap-worktree.sh` exited 144 (frontend node_modules step). Per the existing recurrence (N=4+ — Phases 4/5/6/7 same shape), the resolution is to invoke `/Users/rapha/.../noctusai/venv/bin/python -m pytest ...` directly; the bootstrap failure does not affect backend test execution. No new project filed — `projects/mcp-worktree-path-resolution/` covers this surface.
- **P2 — `verify-the-seed-ships-it` spot-checks confirmed canonical shape.** Re-read `seed/lib/backend/noctusai_lib/integrations/google_calendar/__init__.py` + `oauth_adapter.py` and `seed/lib/backend/noctusai_lib/integrations/google_maps/__init__.py` + `static_adapter.py` + `google_maps_adapter.py`. Both seed modules ship the canonical Protocol+Fake+Real+factory shape (per `KB § PATTERNS/seed-fake-real-adapter.md`). No carve-out required at the seed level. Consumer-side work (credential resolver + travel_lookup bridge) is product-specific by design — the seed docstrings explicitly say location-id semantics are consumer-side.

### Phase 9 — Cancellation + reschedule flows ✅

- [x] Intent variants for cancel + reschedule wired in system prompt — `app/prompts/scheduling_bot.md` declares both tools with pt-BR descriptions + explicit "ask for confirmation before invoking" guardrail (lines 36-66; never invoke without "SIM claro do corretor").
- [x] Tools: `cancel_appointment`, `reschedule_appointment` — registered in `app/services/tool_registry.py` (OpenAI tool descriptors lines 159-235) + live implementations `_impl_cancel_appointment` / `_impl_reschedule_appointment` (lines 456-560) bridge to `SchedulingService.cancel_appointment` / `SchedulingService.reschedule_appointment`. Stub fallbacks preserved for tests bypassing the live wiring (dispatch-loop tests still pass).
- [x] Conversation flow: confirmation step is *prompt-level* (not state-machine). Production-readiness Phase 10 will revisit if confirmation slip-through is observed in production. Prompt enforces: "Reformule de forma simples antes de pedir a confirmação. Pedidos ambíguos ('acho que vou cancelar...') NÃO autorizam a chamada."
- [x] Service methods: `SchedulingService.cancel_appointment(appointment_id, reason?, requester_user_id?)` returns `CancellationResult(cancelled, appointment_id, calendar_deleted, reason)`. `SchedulingService.reschedule_appointment(appointment_id, new_start_at, new_end_at, requester_user_id?)` returns `RescheduleResult(rescheduled, appointment_id, calendar_updated, reason)`. Both flip DB status FIRST (durable) + best-effort Calendar I/O SECOND (failure tolerated; DB stays cancelled/rescheduled). Reschedule re-validates the new slot via `DefaultConflict` with the row's own appointment excluded from the conflict interval set.
- [x] `calendar_event_canceler` + `calendar_event_updater` constructor seams added to `SchedulingService` (consumer-injection Protocol shape; matches Phase 8's `calendar_event_factory` pattern). `app/services/calendar.py` adds `cancel_calendar_event(event_id)` + `update_calendar_event(event_id, start_at, end_at)` thin wrappers around the seed adapter. `app/services/conversation.py::configure_conversation_module` wires both seams from `get_calendar_module()` (same try/except module-not-configured pattern as Phase 8).
- [x] Migration 002 (`products/imobi-scheduling/backend/migrations/002_appointment_audit_columns.sql`) adds `cancellation_reason / cancelled_at / cancelled_by / rescheduled_at / rescheduled_by / previous_start_at / previous_end_at` to `imobi_scheduling.appointments` with `IF NOT EXISTS` guards. **Single-001 convention preserved**: the columns are ALSO inlined into the canonical 001 file (Phase 9 edit-in-place per `KB § PATTERNS/database-rls.md § Single 001 migration`) — greenfield re-runs 001 alone reproduce the full shape; 002 is the live-DB additive patch only. Applied via Supabase MCP (`apply_migration` 2026-05-11); all 7 columns present in live DB.
- [x] 16 new tests at `tests/services/test_scheduling.py` — 6 `TestServiceCancelAppointment` (audit columns / not-found / idempotent already-cancelled / calendar-canceler wired / calendar-failure tolerated / event-id-absent skip) + 6 `TestServiceRescheduleAppointment` (audit columns / not-found / end-before-start / new-slot-conflict / calendar-updater wired / calendar-failure tolerated) + 4 misc shared with confirm flow. Full suite **308 passed** (was 292 Phase 8 baseline; +16).
- [x] `python mcp/noctusai/cli.py --review --product imobi-scheduling` → **0 issues**.

**Improvements:**
- **P0 — Seed schema-cache repo-root resolution breaks under worktree isolation.** `noctusai_lib.testing._schema_cache._find_repo_root()` walks parents from `Path(__file__)` (the seed module's install location). When run via the shared canonical venv (worktree convention), `__file__` resolves to `/Users/.../noctusai/seed/lib/backend/...`, so the walk finds canonical noc's `products/`, not the worktree's. Result: the mock validates against canonical noc's stale migrations, blocking any worktree-local schema additions. **Worktree-local fix applied at `products/imobi-scheduling/backend/tests/conftest.py`**: import-time `_prime_schema_cache_from_worktree()` walks from `__file__` of the *conftest* (which IS in the worktree), parses every `products/*/backend/migrations/*.sql` it sees, and `set_cache_for_tests(...)` overrides the module cache before any test runs. **Cross-product follow-up filed against `projects/mcp-worktree-path-resolution/`** — the seed-level fix is to flip `_find_repo_root` to prefer `NOCTUSAI_REPO_ROOT` env var before the walk (currently used only as fallback). DDD's-stall root cause; resolution unblocks all worktree-isolated tests that touch newly-added columns. **N=2 confirmed** — same shape as the MCP scaffold-tool worktree-path slip (`projects/mcp-worktree-path-resolution/`). N=3+ moves the seed-level fix from "open follow-up" to "must ship now".
- **P1 — Conversation-flow confirmation is prompt-level, not state-machine.** Today the bot's "ask before write tool" guardrail lives in `app/prompts/scheduling_bot.md` prose. A determined-but-confused LLM could still call `cancel_appointment` without the SIM, especially under prompt-injection. **Defer to Phase 11 (security-hardening)** — that phase will add a prompt-injection test suite + output sanitization; a confirmation-state-machine wrapping `cancel_appointment` / `reschedule_appointment` is the right complement. Surface in `KB § PATTERNS/llm-bot-security.md` (Phase 11 NEW pattern doc).
- **P1 — Audit-column-population symmetry.** `cancel_appointment` writes `cancellation_reason` + `cancelled_at` + `cancelled_by`. `reschedule_appointment` writes `rescheduled_at` + `rescheduled_by` + `previous_start_at` + `previous_end_at` BUT does NOT capture a `reschedule_reason` (no equivalent column was specified). If the user/LLM provides a reschedule rationale ("queue jammed, move to next week"), we lose it. Surface candidate: add `reschedule_reason TEXT` to migration 003 + plumb through `reschedule_appointment(..., reason: str | None)` signature. **Deferred to a Phase 10 production-hardening item** — not blocking Phase 9 close; symmetry win when surfaced by N=1 production user.
- **P2 — Calendar best-effort semantics deliberate.** Both flows flip the DB first + then attempt Calendar I/O. Failure tolerated. The opposite ordering (Calendar first + DB second) would risk DB-Calendar drift the OTHER way (Calendar updated but DB unchanged → user sees the new slot in their calendar but the booking system thinks it's still in the old slot). The chosen ordering aligns with Phase 8's `confirm_appointment` calendar-create-aborts-on-failure model: **write-path failures abort; cleanup-path failures don't**. Documented in service-method docstrings.
- **P2 — `_prime_schema_cache_from_worktree` is product-local.** Logging here for cross-product lift: when N=2 product hits the same worktree-CWD pollution, this conftest snippet is the lift candidate to `noctusai_lib.testing.worktree_aware_schema_cache_setup()` — single import + single call in product conftest. **Defer until N=2**; documented inline in conftest.py prose so the lift trail is discoverable.
- **P3 — Worktree-venv recurrence N=5+.** Same as Phases 4-8: `pytest` against the canonical venv path. Resolution unchanged. Existing `projects/mcp-worktree-path-resolution/` covers it. Not filing again.

### Phase 10 — Production hardening ✅

- [x] **Retries on transient failures.** New `app/services/retry.py` ships `retry_call(callable, *, policy, transient_exceptions, sleep, label)` composing the seed's `noctusai_lib.domain.jobs.retry_policy.RetryPolicy` (exponential-backoff math from the seed; the wrapper is product-side at N=1 consumer — seed-side lift filed for N=2). Two product constants: `RETRY_POLICY_CALENDAR` (3 retries / 1s base / 2x / 30s cap) + `RETRY_POLICY_WAHA` (3 / 0.5s / 2x / 10s cap). Wired into `app/services/calendar.py` at all three adapter call sites — `create_calendar_event` / `cancel_calendar_event` / `update_calendar_event`. Same deterministic `request_id` is reused across retries so wire-level idempotency (once the seed-side guard lands per the Phase 8 P0 follow-up) collapses duplicates; until then the consumer-side DB-pre-check is the line of defense. WAHA outbound retry is **preparatory** — outbound send is not yet wired (Phase 6 deferred emission); when it lands, wrap with `retry_call(... policy=RETRY_POLICY_WAHA ...)`.
- [x] **Structured logs.** Already wired by the seed — `create_product_app(...)` calls `noctusai_lib.logging_config.configure_logging(debug=..., json_logs=..., app_name=...)` at `seed/framework/backend/noctusai_seed/app.py:146`. The product ships `app/logging_config.py` as a thin re-export of `noctusai_lib.logging_config.*` (matches the 4-product convention — core/ERP/PF/therapy). No product source uses `print(...)` or `logging.basicConfig(...)`; every module uses `logger = logging.getLogger(__name__)`. JSON output is automatic in production (`debug=False`).
- [x] **Deployment target documented.** New `products/imobi-scheduling/DEPLOYMENT.md` (6 sections per the operational-readiness pattern): Target (Compose / k8s decision) → Ports → Environment variables (table: name | purpose | secret? | default) → Health check (Compose `healthcheck:` block) → Logging → DB backup procedure → Retry semantics → Metrics → Smoke test. Authoritative operational runbook until Phase 12 folds the relevant subset into the README.
- [x] **DB backup procedure documented.** Inline in `DEPLOYMENT.md` § 6: Supabase managed daily backups (Pro+ tier, PITR-capable); restore path documented (Dashboard → Database → Backups → Restore); critical tables enumerated (`appointments` / `appointment_requests` / `users` + `linked_identities` / `oauth_credentials` / `tool_call_audits`); manual `pg_dump --schema=imobi_scheduling` recipe as the disaster-recovery drill; conversation memory called out as ephemeral by design (Redis TTL-bound; not part of the backup contract).
- [x] **Health-check endpoint.** Covered by `standard_routers=["health", "notificacoes", "team"]` in `app/main.py`. Verified via existing `tests/routers/test_health.py` (status-pinned). Compose `healthcheck:` block specified in `DEPLOYMENT.md` ready for substitution into the slug-renamed compose file.
- [x] **Metrics sink — deferred-with-destination.** New `app/services/metrics.py` ships the seam: `Counter` Protocol (`@runtime_checkable`) + `NoopCounter` default (DEBUG-level structured-log lines — `metric.increment name=... value=... tags=...` — so events are observable without a real backend) + `configure_counter(counter)` lifespan-swap point + semantic helpers `record_tool_dispatch(tool_name, *, success)` + `record_llm_call(*, model, success)`. **Rationale for shipping the seam now even though the default is no-op**: backfilling metric call sites later is a cross-cutting refactor; wiring them today (with the no-op default) lets the future `projects/platform-metrics/` follow-up ship a one-line lifespan change. Cost near-zero today; saves a refactor later. **N=2 destination**: `noctusai_lib.observability.counter` (likely OpenTelemetry given the multi-export story); follow-up filed below.
- [x] **NEW pattern doc.** `KNOWLEDGE-BASE/CONTEXT/PATTERNS/chatbot-operational-readiness.md` ships (9 sections): The 6 pillars table + per-pillar treatment (retries / structured logs / health / deployment doc / backup / metrics sink) + adoption checklist + first-adopter cross-reference. Indexed in `KNOWLEDGE-BASE/INDEX.md` (Layout tree + patterns table); pointed at from `CLAUDE.md § 2 The Map` (Patterns subsection). `verify-kb-sync.sh` green.
- [x] **Tests.** 18 new tests (`tests/services/test_retry.py` × 11 + `tests/services/test_metrics.py` × 7) — `pytest products/imobi-scheduling/backend/ -q` → **326 passed** (was 308 Phase 9 baseline; +18).
- [x] `python mcp/noctusai/cli.py --review --product imobi-scheduling` → **0 issues**.
- [x] `bash scripts/verify-kb-sync.sh` → green.
- [x] Live deploy smoke — **DEFERRED** to user deploy drill (no real Calendar / WAHA credentials in the worktree).

**Improvements:**
- **P0 — Seed gap: in-flight retry wrapper.** The seed ships `RetryPolicy` (math) but no `retry_call(...)` wrapper — `RetryPolicy` is currently consumed only by the queue-job worker which re-enqueues failed jobs. For in-flight blocking calls (HTTP write, calendar API) the consumer needs a synchronous wrapper. Shipped product-side at `app/services/retry.py` as N=1 consumer; **N=2 destination** is `noctusai_lib.primitives.retry` (stateless helper → primitives layer per `KB § PATTERNS/seed-lib-layout.md`). File the seed lift when mailing's outbound send / therapy's calendar invites need the same shape.
- **P1 — Phase 0 leftover: docker-compose.yml + Dockerfile still seed-named.** `products/imobi-scheduling/docker-compose.yml` declares services `seed-backend` / `seed-frontend` / `seed-tunnel` with container names `noctus-seed-*` (the scaffold copy was not substituted at Phase 1 scaffold time). Same shape in `backend/Dockerfile` header comments. Operator-visible: `docker compose up` works (the fragment is self-contained), but the cosmetic mismatch is a Phase 12 cleanup item (or a follow-up scaffold-tool fix to substitute slugs at copy time — N=2 if any future scaffolded product hit the same gap, surface candidate for `noctus.dev.scaffold_product` post-copy substitution pass). Flagged in `DEPLOYMENT.md` so an operator reading it isn't confused.
- **P1 — Metrics sink platform-wide lift.** Filed as `projects/platform-metrics/` (TBD slug) follow-up. Trigger: N=2 product (therapy / mailing) needs counter events. Destination: `noctusai_lib.observability.counter` Protocol + OpenTelemetry-backed real adapter + lifespan-startup wire. The `app/services/metrics.py` seam absorbs into the seed verbatim; the consumer code (call sites) stays as-is.
- **P1 — `IMOBI_WHATSAPP_WEBHOOK_SECRET` unset → verification bypassed + WARN.** Documented in `DEPLOYMENT.md` env-vars table as "Set in prod." Production deployments without the secret silently accept any signature (the seed router's `bypass_when_unset` shape, per `KB § PATTERNS/webhook-signatures.md`). The WARN log is the line of defense; operators must read the startup log. Surface candidate for a `health` route extension that reports lifespan-state ("webhook_hmac=configured" vs "bypass") so deployment health checks catch the misconfiguration without scanning logs.
- **P2 — Backup-restore drill not yet executed.** The recipe is documented; the actual `pg_dump → psql` restore against a fresh Supabase project has not been exercised end-to-end. **First production deploy** is the natural moment to run it (capture timing + edge cases in the runbook). Deferred to the deploy drill rather than blocking Phase 10 close.
- **P2 — WAHA outbound emission still deferred.** Phase 6 explicitly deferred outbound send to a follow-up phase (the conversation worker logs the reply but doesn't emit). When outbound lands, wrap the `send_text_sync(...)` call with `retry_call(... policy=RETRY_POLICY_WAHA ...)` per the doc. Surface candidate for inclusion in the README "operational" subsection at Phase 12.
- **P2 — Health endpoint reports only "up", not "wired".** Today `GET /api/health` returns 200 as long as the FastAPI app booted. A half-wired startup (missing `SUPABASE_SERVICE_ROLE_KEY` → conversation module not configured → inbounds dropping) still reports healthy. Documented in `KB § PATTERNS/chatbot-operational-readiness.md § 4` as a future enhancement candidate; deferred until N=2 products surface the same gap.
- **P3 — Worktree-venv recurrence N=6+.** Same as Phases 4-9: `pytest` against the canonical venv path. Resolution unchanged. Existing `projects/mcp-worktree-path-resolution/` covers it. Not filing again.

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

## 7. Open questions — ✅ Q1-Q5 resolved 2026-05-10 (orchestrator-stamped defaults)

1. **Product slug?** ✅ **`imobi-scheduling`** confirmed 2026-05-10 (orchestrator-stamped default).
2. **Port allocation?** ⏳ **Engineer picks next available** from `KB § 05-INFRASTRUCTURE.md` during Phase 0 audit; logs in §11. (No user decision needed — it's a registry pick.)
3. **Frontend in v1?** ✅ **DEFER** — WhatsApp-only v1; admin UI is a follow-up project. Orchestrator-stamped 2026-05-10.
4. **Single-agency or multi-tenant?** ✅ **single-agency v1** (multi-tenant is a refactor when a second agency arrives). Orchestrator-stamped 2026-05-10.
5. **Standalone or paired with `erp-imobiliario`?** ✅ **standalone product** — shares conventions with erp-imobiliario; cross-product data is a future integration concern. Orchestrator-stamped 2026-05-10.
6. **Localization in v1 (pt-BR + en)?** Recommendation: **pt-BR only**; localization framework is a future seed concern. Decided in Phase 6.
7. **LGPD posture?** Run the five questions (`KB § PATTERNS/lgpd.md`) over conversation message storage + tool audit rows. Recommendation: conversation messages are PII (phone, name, possibly location); tool audit rows hold the same; document basis + retention in Phase 12 KB doc. Apply `noctus.dev.lgpd_flag(...)` if uncertain.
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
python mcp/noctusai/cli.py noctus.dev.scaffold_product --slug=<confirmed-slug>

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
| 2026-05-10 | **Phase 0 design decisions stamped by orchestrator** under user signal "resolve the 5 blocked ones". Defaults accepted: Q1 slug `imobi-scheduling`; Q3 frontend deferred (WhatsApp-only v1); Q4 single-agency RLS; Q5 standalone product. Q2 port allocation deferred to engineer's Phase 0 audit (registry pick, no user decision needed). All 4 substrate seed projects confirmed shipped — Phases 5-8 dependency unblocked. Phase 0 (sibling audit) + Phase 1 (scaffold) dispatched. | claude-opus-4-7 |
| 2026-05-10 | **Phase 3 (domain models + migrations) closed by engineer.** 15 domain tables landed in single 001 migration (`products/imobi-scheduling/backend/migrations/001_imobi_scheduling.sql`): users / condominiums / properties / services / crew_skills / appointment_requests / appointment_request_services / route_groups / appointments / conversation_messages / conversation_summaries / pending_chat_identities / oauth_credentials / routes / tool_call_audits. Per-schema `set_updated_at()` function declared once, BEFORE-UPDATE triggers on each mutable table. RLS single-agency v1 (Phase 0 Q4): every table SELECT/INSERT/UPDATE/DELETE scopes via `org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid` subquery form; UPDATE policies pin WITH CHECK; append-only tables (`conversation_messages`, `tool_call_audits`) omit UPDATE policies. Applied via Supabase MCP (`apply_migration` × 2 — initial + missing-FK-index follow-up). All 17 tables live with RLS enabled. 10 Pydantic schema modules (`users / condominium / property / service / appointment / conversation / pending_chat_identity / oauth_credential / route / tool_call_audit`) with Create/Update/Out variants + `model_validator` invariants (e.g. appointment `end_at > start_at`). **125 new structural tests** (89 migration parse + 36 schema validation): full suite 166 green (was 41). `noctus.dev.review --product imobi-scheduling` clean. Advisor INFOs: 4 unindexed_FK (fixed inline), 51 unused_index (expected no-traffic baseline). | engineer-subagent |
| 2026-05-10 | **Phase 0 (audit) + Phase 1 (scaffold) closed by engineer.** Port allocation Q2: backend `8011` / frontend `8160` (picked via `noctus.dev.available_ports` — next contiguous slot after `youtube-crawler` on 8010/8150; rationale: lowest free pair in each band per registry of record `RESERVED_RANGES`). Scaffold via `noctus.dev.scaffold_product`: 58 files at `products/imobi-scheduling/`, seed-row migration `028_seed_imobi_scheduling_product.sql`, `start.sh` + root `docker-compose.yml` registration. 41/41 smoke tests green. **Q3 frontend-deferred carve-out logged as accept-with-rationale:** scaffold tool always emits a frontend skeleton; the v1 frontend folder is a placeholder (no admin UI built, no route wiring beyond seed defaults); future "v1 admin UI" follow-up project will either populate it or formally delete. **Surfaced as MCP-toolkit gap:** the scaffold tool has no `--backend-only` opt-out flag — every product gets a frontend even when product semantics don't need one (recurrence candidate: this is N=2 with `youtube-crawler` which also has a near-empty frontend; flag for `noctus.dev.scaffold_product` enhancement). **Critical worktree finding (P0):** scaffold tool path-resolved to canonical noc root (`/Users/.../noctusai/`), not the isolated worktree filesystem (`.claude/worktrees/agent-.../`). Workaround applied: copied output into worktree + mirrored `start.sh` + root `docker-compose.yml` edits. Methodology gap — MCP scaffold tools use `REPO_ROOT` from `settings`, bypassing worktree isolation. See `findings.md` §1+§5 for full slip detail. | engineer-subagent |
| 2026-05-11 | **Phase 7 (scheduling-engine wiring) closed by engineer.** New product module `app/services/scheduling.py` (`build_rules(settings)` → `SchedulingRules`, `build_engine(rules, travel_lookup, ...)` → `SchedulingEngine`, `SchedulingService` orchestrator owning `lookup_property` + `propose_appointment` + `confirm_appointment`). Real-estate vocabulary mapping: location=condominium_id, assignee=media_crew_user_id, transition=travel_buffer. Phase 6 stubs replaced with DB-backed implementations in `app/services/tool_registry.py` (live impls dispatched via `_LIVE_IMPLEMENTATIONS` when a `SchedulingService` is injected; no-arg `build_tool_handler()` still runs the stubs so existing dispatch-loop tests keep passing). `app/services/conversation.py` + `app/lifespan.py` wire the service into the `ConversationModule`. `app/config.py` Phase 7 knobs promoted to LIVE; afternoon-end fixed `18:00` → `16:30` per brief / Engineer-E audit. Lunch (12:00-13:30) is IMPLICIT as the gap between two named `WorkingWindow`s — no `BlockedInterval` needed. **Custom Conflict + Maps-backed scorer DEFERRED**: `DefaultConflict` covers MVP semantics; `GoogleMapsTravelLookup` wires at Phase 8 via constructor seam already in place. Calendar event creation deferred to Phase 8 (passthrough `google_calendar_event_id` argument). **24 new tests** (21 `test_scheduling.py` + 4 `test_tool_registry.py` live-service dispatch): full suite 261 green (was 237 baseline). Keeper `--review --product imobi-scheduling` → 0 issues. Worktree-venv recurrence N=4+ (still tracked in `projects/mcp-worktree-path-resolution/`). | engineer-subagent |
| 2026-05-11 | **Phase 6 (chatbot framework + tool-audit wiring) closed by engineer.** New product modules: `app/services/conversation.py` (the `ConversationModule` container + `configure_conversation_module(...)` factory + `start_worker()` / `stop_worker()` lifecycle hooks), `app/services/tool_audit.py` (`make_supabase_audit_writer(admin_client, org_id, ...)` — Supabase adapter to the seed's `AuditRecord` shape; bridges the `LLMDispatcher.AuditWriter` 2-arg signature → 1-arg `AuditRecord`), `app/services/tool_registry.py` (3 OpenAI tool descriptors + stub impls + handler closure), `app/lifespan.py` (idempotent on_startup/on_shutdown wired into `main.py` via `create_product_app(..., lifespan_startup=..., lifespan_shutdown=...)`), `app/prompts/scheduling_bot.md` (pt-BR system prompt prose; ported from sibling). Worker started via `schedule_coro(_run_worker_in_thread(worker), name=...)` per memory rule — wrapper around `asyncio.to_thread(worker.run_forever)` because the seed worker is **synchronous**. **Two seed gaps surfaced (both P0):** (1) `configure_conversation_module` does not exist at the seed level — chatbot module is constructor-based; consumer-side wiring lands in this product as the carve-out shape, lift at N=2; (2) `default_audit_writer(db)` does not exist — seed ships `make_audit_writer(db, table_class)` for **SQLAlchemy Session** only; product is **Supabase-client based**, so we ship the Supabase adapter consumer-side. **38 new tests** (10 tool_audit + 13 tool_registry + 11 conversation + 4 lifespan): full suite 237 green (was 199 baseline). Keeper `--review --product imobi-scheduling` → 0 issues. `dispatcher.AuditWriter` signature mismatch with `AuditRecord` callable shape catalogued as P1 follow-up against `noctusai_lib.domain.ai.tool_audit`. Worktree-venv recurrence N=3+ (noted P2). | engineer-subagent |
| 2026-05-11 | **Phase 9 (cancellation + reschedule flows) closed by Engineer DDD (WIP) + DDD2 (finisher).** DDD landed the bulk of Phase 9 (service methods + tests + tool descriptors + prompt updates + migration 002 + calendar wrappers) and was killed by the 600s watchdog mid-debug on the 7 failing tests. DDD2 picked up the WIP at branch `origin/worktree-agent-aace1824ecc6b6b2c` (commit 8215526), imported it into the engineer worktree, diagnosed root cause, and shipped the fix + verifications. **Root cause of DDD's 7 failures**: `noctusai_lib.testing._schema_cache._find_repo_root()` walks parents from the seed module's `__file__` location — under worktree isolation that resolves to canonical noc (the shared venv install location), NOT the worktree's `products/` dir. Result: the schema cache was validated against canonical noc's stale migrations (which lack Phase 9 audit columns), so every UPDATE writing `cancellation_reason / cancelled_at / rescheduled_at / etc.` hit `MockSchemaError`. **DDD2 fix**: worktree-local `_prime_schema_cache_from_worktree()` at `products/imobi-scheduling/backend/tests/conftest.py` walks from the conftest's own `__file__` (which IS in the worktree), parses every `products/*/backend/migrations/*.sql` under it, and calls `set_cache_for_tests(...)` at conftest import time — overrides the module cache before any test runs. **Service code**: `SchedulingService.cancel_appointment` / `.reschedule_appointment` + 7 audit columns inlined into 001 + migration 002 additive patch + `calendar_event_canceler` / `calendar_event_updater` consumer-injection seams + `cancel_calendar_event` / `update_calendar_event` wrappers at `app/services/calendar.py`. **Migration 002** applied via Supabase MCP — 7 audit columns live in `imobi_scheduling.appointments`. **16 new tests** (12 Phase 9 + supporting): full suite **308 passed** (was 292 Phase 8 baseline; +16). Keeper `--review --product imobi-scheduling` → 0 issues. **Seed-level follow-up filed** (P0 in §6 Improvements) — `_find_repo_root` should prefer `NOCTUSAI_REPO_ROOT` env over the parent-walk when both are present; N=2 surfaced (same shape as MCP scaffold-tool worktree-path slip already tracked in `projects/mcp-worktree-path-resolution/`). | engineer-subagent (DDD + DDD2) |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) WILL BE DELETED by the user once the absorption batch (this project + the four seed projects) is complete. This project's success requires:

- **No sibling-path references survive** in product code, KB docs, MASTER-PROMPT, or README. Sibling refs in this PROJECT.md are execution-scoped — the project folder gets deleted on close per apply-inline-then-delete.
- **No symlinks, no editable installs, no path deps** to the sibling. The product's `pyproject.toml` declares deps on `noctusai_lib` (in our seed) only.
- **Tests stand alone.** Any test fixture inspired by sibling tests is rewritten to the product's data shape.
- **Phase 14's go-live verification includes a sibling-deletion safety check.** The project does not close until that check passes.
