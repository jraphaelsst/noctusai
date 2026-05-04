# Media Scheduling — Port from external repo to noc product (resumed)

- **Created:** 2026-05-03 (original) / 2026-05-04 (resumed in dedicated worktree)
- **Last updated:** 2026-05-04
- **Status:** Phase 0 ✅ + Phase 0.5 ✅ + Phase 1 ✅ + Phase 2 ✅ + Phase 3 ✅ + Phase 4 ✅ + Phase 5 ✅ → Phase 6 + Phase 7 ahead
- **Owner / stakeholders:** joaoraphaelsst@gmail.com · claude-opus-4-7
- **Worktree:** `/Users/rapha/Documents/repository/NoctusAI/noctusai-worktrees/media-scheduling-port-resume/` (per worktree-per-engineer rule)
- **Branch:** `media-scheduling-port-resume` (off `origin/main` at `062853b`)
- **Related docs:** `MEDIA-SCHEDULING-PORT-LOG.md` (worktree root — live narrative + collision case study) · `findings.md` (this folder — curated lessons) · `KB § PATTERNS/seed-fake-real-adapter.md` (canonical pattern, shipped during this project) · `KB § PATTERNS/whatsapp-chatbot-seed.md` · `KB § PATTERNS/scheduling-seed.md` · `KB § PATTERNS/llm-tool-audit.md` · `KB § PATTERNS/webhook-signatures.md`
- **Project slug:** `media-scheduling-port` (lives at `projects/media-scheduling-port/` — root location because the work creates a product that doesn't exist yet)

---

## 1. Context & Purpose

Mature standalone FastAPI service at `/Users/rapha/Documents/repository/NoctusAI/whatsapp-google-scheduling/` (sibling of noc) schedules real-estate content production appointments (media-crew → properties at condominiums) from real WhatsApp users into Google Calendar. The conversational side is real WhatsApp ↔ OpenAI GPT exchanges via WAHA — production data, not test fixtures.

**The win.** Bring it into noc as a fully-seeded product (`products/media-scheduling/`) so it inherits the seed framework (factories, SSO, observability, MCP toolkit reach, deploy infra, KB depth) AND so the seed surfaces it exercises (`whatsapp`, `chatbot`, `scheduling`, `google_calendar`, `google_maps`, `webhook_signatures`, `llm-tool-audit`) get their first **real-runtime consumer** — testing the "verify the seed ships it" rule under load. The port is the platform's correctness check on the seed.

---

## 2. Confirmed constraints

- **Code shape — "exactly the seed, nothing out of pattern"** (user). Out-of-pattern code = stop and triage.
- **DB — Supabase**, not SQLAlchemy/Alembic. Numbered migrations mirrored via Supabase MCP.
- **Auth — split surface**: SSO `authProvider` for admin; LID-aware first-inbound on WAHA webhook (accept-with-rationale).
- **Frontend — thin admin** at same maturity as backend.
- **`mcp_server/` from source** — already absorbed in a prior session; out of scope.
- **`tool_call_audit`** — seed pattern (`AuditRecord` + `make_audit_writer`).
- **Webhook HMAC** — `noctusai_lib.security.webhook_signatures`.
- **Source repo fate** — leave alone until green-bar verification.
- **Real production conversations in source DB** — Phase 2 preserves data fidelity (real WhatsApp ↔ OpenAI exchanges, not mock).
- **Process artifact** — single rich tracking log at worktree root (`MEDIA-SCHEDULING-PORT-LOG.md`); curated lessons at `projects/media-scheduling-port/findings.md` per the `feedback_knowledge_tracking.md` rule.
- **Worktree-per-engineer** (post-collision learning) — dedicated worktree at `noctusai-worktrees/media-scheduling-port-resume/`. Per-phase commit cadence (not project-end-only) to reduce blast radius.

---

## 3. Design principles

1. **Phase 0 (audit) → Phase 0.5 (seed backfill) → Phase 1 (scaffold).** Audit surfaces gaps. Phase 0.5 fixes seed gaps in canonical Fake+Real shape. Phase 1 scaffolds against a fully-shaped seed.
2. **Port-onto-seed, not port-as-is.** Every service that maps to a seed module consumes `noctusai_lib.*`. Product side shrinks to genuinely real-estate-specific bits.
3. **Two-surface auth** — SSO admin + LID webhook. Documented + accept-with-rationale.
4. **Real-estate-specific scheduling logic plugs into seed engine via Protocols** (`Conflict` / `Scorer` / `TravelLookup`).
5. **Tests preserved + extended.** Source unit tests ported. New seed-consumption integration tests added.
6. **Per-phase commit cadence** — collision learning. Each phase ends with a local commit on `media-scheduling-port-resume` branch.

---

## 3a. Seed-first analysis ✅

1. **Contract identical for every product?** MIXED. Infrastructure contracts (whatsapp, scheduling, calendar/maps, redis, webhook HMAC, audit) are uniform — already in seed. Domain contracts (condominium travel, crew-skill matching, media-service durations) are unique to this product.
2. **Data source product-specific?** YES — real-estate-media domain.
3. **Placement product-specific?** YES — admin UI lives at `products/media-scheduling/frontend/`; webhook router mounted via `standard_routers=[...]` on this product's backend.
4. **Visibility / permission rule the same?** MIXED — SSO uniform on admin; LID-aware on webhook (accept-with-rationale).
5. **Seam exists in seed?** YES, all known seams ship — `create_product_app(standard_routers=, lifespan_startup=, authProvider=)`, `noctusai_lib.integrations.whatsapp.*`, `noctusai_lib.domain.chatbot.*`, `noctusai_lib.domain.scheduling.*`, `noctusai_lib.integrations.{google_calendar, google_maps}`, `noctusai_lib.security.webhook_signatures`. Phase 0 confirmed runtime-ready in canonical Fake+Real shape (after Phase 0.5 closes the three gaps).
6. **Default-on or opt-in?** OPT-IN per product — not every product needs WhatsApp-driven scheduling.

**Litmus:** the design is correctly product-bounded. No lines that should be in seed but aren't (after Phase 0.5).

---

## 4. Scope

**In scope.** New product `products/media-scheduling/` (backend + thin admin frontend at same maturity), schema in Supabase `media_scheduling` schema, WAHA inbound + Redis buffer + LLM-dispatch worker via seed, scheduling engine + Calendar/Maps adapters via seed, LID-aware webhook auth (accept-with-rationale), HMAC verify via seed, tool-call audit via seed pattern, KB landscape update, MEDIA-SCHEDULING-PORT-LOG.md + findings.md narrative artifacts.

**Out of scope.** Source repo deletion (deferred until green-bar in real WhatsApp traffic). `mcp_server/` from source (already absorbed). Production deploy (separate project). Extending seed beyond Phase 0.5 gaps (each future gap files its own follow-up project). Historical data migration (separate project).

---

## 5. Architecture / Data Model

### Repo layout (after this project)

```
products/media-scheduling/
├── README.md
├── MASTER-PROMPT.md
├── projects/
├── proposals/
├── backend/
│   ├── app.py                      # create_product_app(standard_routers=[webhooks_router, oauth_router, admin_routers...], lifespan_startup=worker_lifecycle, authProvider=seed_sso)
│   ├── routers/
│   │   ├── webhooks.py             # WAHA inbound — HMAC verify → seed parser → seed buffer
│   │   ├── oauth.py                # Google OAuth → OAuthCredential
│   │   ├── appointments.py         # admin CRUD
│   │   └── authorized_users.py     # admin CRUD
│   ├── services/
│   │   ├── scheduling_adapters.py  # product-side Conflict / Scorer / TravelLookup adapters
│   │   ├── crew_assignment.py      # real-estate crew-skill matching
│   │   └── condominium_travel.py   # same-condominium duration logic
│   ├── workers/
│   │   └── conversation_worker.py  # consumes seed chatbot.worker primitive
│   ├── migrations/
│   │   ├── 001_initial_schema.sql
│   │   ├── 002_rls.sql
│   │   ├── 003_indexes_fks.sql
│   │   └── 004_seed_data.sql
│   └── tests/
└── frontend/
    └── src/
        ├── app.tsx                 # createProductApp(authProvider=seed_sso, ...)
        └── pages/
            ├── AppointmentsPage.tsx
            ├── AuthorizedUsersPage.tsx
            └── OAuthStatusPage.tsx
```

### Schema (target — Supabase `media_scheduling` schema)

| Source SQLAlchemy model | Target Supabase table |
|---|---|
| `User` | `media_scheduling.authorized_users` |
| `Appointment` | `media_scheduling.appointments` |
| `Property` | `media_scheduling.properties` |
| `Condominium` | `media_scheduling.condominiums` |
| `ServiceType` | `media_scheduling.service_types` |
| `CrewSkill` | `media_scheduling.crew_skills` |
| `Route` | `media_scheduling.routes` |
| `Conversation` | *(replaced by chatbot seed primitives)* |
| `ConversationSummary` | `media_scheduling.conversation_summaries` |
| `OAuthCredential` | `media_scheduling.oauth_credentials` |
| `PendingChatIdentity` | `media_scheduling.pending_chat_identities` |
| `ToolCallAudit` | `media_scheduling.tool_call_audits` (seed `AuditRecord` writes) |

---

## 6. Implementation phases

### Phase 0 — Seed-completeness audit ✅

(Results in `MEDIA-SCHEDULING-PORT-LOG.md § 1`. All 8 modules runtime-ready; 3 gaps surfaced (G1-G3) + 1 DRY violation (G4); gold-standard pattern documented.)

**Improvements:**
- Future seed audits should default to listing-then-reading every sibling module alongside, not just the one being consumed — the recurrence rule fires inside seed too. (Surfaced lesson L2 in findings.md.)

### Phase 0.5 — Seed-pattern backfill ✅

- [x] **G1** — `integrations.whatsapp`: `WhatsAppClient` Protocol in `types.py` + `FakeWahaClient` (bi-directional) + `get_whatsapp_client()` factory + 18 tests.
- [x] **G2** — `integrations.redis`: `make_fake_redis_client()` (wraps `fakeredis.FakeStrictRedis`) + 7 tests + `fakeredis>=2.20.0` dep.
- [x] **G3** — `domain.chatbot.buffer`: `make_in_memory_buffer_client()` (re-exports redis fake) + 4 tests + `@runtime_checkable` retrofit on `RedisBufferClient` Protocol.
- [x] **G4** — Hard-deleted `noctusai_lib/domain/conversation/` + `tests/domain/conversation/`.
- [x] **CLAUDE.md** — §1 universal rule bullet for the Fake+Real pattern landed.
- [x] **Tests** — 88 passing (28 new + 60 existing chatbot/whatsapp/redis regression).
- [x] **Per-phase commit** — `2defcfe phase(media-scheduling-port-resume): Phase 0.5 ✅ — seed Fake+Real backfill (G1-G4) + project setup`.

**Improvements:**
- The existing seed `RedisBufferClient` Protocol lacked `@runtime_checkable`. Retrofitted as part of G3 to match `WhatsAppClient` / `CalendarAdapter` / `RoutingAdapter` consistency. **Worth a sweep**: any other seed Protocol classes lacking the decorator? Defer to a follow-up `seed-protocol-runtime-checkable-sweep` project.
- `pre-commit` hook falls back to system `python3` when `$REPO_ROOT/venv/bin/python` is absent — and a fresh worktree has no `venv/` directory (the venv lives in the main worktree). Workaround: `PYTHON=/path/to/main-venv/python git commit ...`. **Better fix:** hook walks up to find the canonical noc venv, OR each worktree gets a venv-symlink at creation. Defer to a follow-up `worktree-venv-isolation` project. Logged via `noctus.dev.phase_learning_log` (methodology kind).
- Editable-install of `noctusai-lib` from this worktree REPOINTED the shared venv's noctusai-lib at the worktree's seed/. Cross-worktree editable contamination is real; venv-per-worktree would eliminate it. Same follow-up project.

*Phase proposal:* none filed (improvements bundle small enough to live as PROJECT.md + findings.md notes; the venv-isolation item is genuinely cross-cutting and deserves its own project at the methodology layer, not a per-phase proposal).

### Phase 1 — Scaffold `products/media-scheduling/` ✅

- [x] **Manually scaffolded** (NOT via MCP `noctus.dev.scaffold_product` — the MCP server's `get_workspace_root()` resolves to the MAIN worktree, would have landed the new product outside this branch). Replicated the scaffold tool logic via `rsync templates/product-seed/ → products/media-scheduling/` + Python walk replacing `{{PRODUCT_NAME}}` → `Media Scheduling`, `{{SCHEMA_NAME}}` → `media_scheduling`, `{{BACKEND_PORT}}` → `8096`, `{{FRONTEND_PORT}}` → `8130`, `{{PRODUCT_ICON}}` → `Calendar`.
- [x] Confirmed `products/media-scheduling/{backend, frontend, projects, README.md, MASTER-PROMPT.md}` landed (41 files; `proposals/` not in template — created lazily on first use).
- [x] Confirmed `backend/app/main.py` calls `create_product_app(name='Media Scheduling', schema='media_scheduling', settings=settings, version='0.1.0', limiter=limiter, standard_routers=['health', 'notificacoes', 'team'])` ✓.
- [x] Confirmed `frontend/src/App.tsx` calls `createProductApp({routes, Layout, ...})` with `createProductLayout(brandIcon=Calendar, brandTitle='Media Scheduling')` ✓.
- [ ] **DEFERRED to Phase 7 close** — `KB § 02-LANDSCAPE.md` product-table entry. Reason: shared tracked file across worktrees; deferring cross-cutting tracked-file edits reduces collision risk while parallel sessions are active (collision learning from Phase 0.5 redo).

**Improvements:**
- **scaffold.py extension filter misses `.env.example`** — `frontend/.env.example` shipped with unreplaced `{{PRODUCT_NAME}}` + `{{BACKEND_PORT}}`. Manually fixed in the commit; flagged as an upstream improvement to `mcp/noctusai/tools/noctus/dev/scaffold.py:57` (add `.example` to the extension tuple, OR shift to a deny-list of binary extensions). Defer to a `scaffold-tool-extension-coverage` follow-up project.
- **MCP `noctus.dev.scaffold_product` not workspace-aware enough for active worktree** — the tool reads `get_workspace_root()` which resolves at MCP-server-startup time. There's no per-call `target_dir=` override. In multi-worktree environments this forces manual scaffolding. Defer to a `mcp-workspace-per-call-override` follow-up project (could be a per-call kwarg on the tool, OR a hook that re-resolves workspace_root on each call).
- **start.sh + vite.config.factory.ts PRODUCT_MAP wiring deferred** — both are tracked files shared across worktrees, same collision-risk reasoning as the LANDSCAPE.md deferral. Phase 7 close handles the batch.

*Phase proposal:* none filed (improvements small + cross-cutting; flagged as deferred-with-named-followup).

### Phase 2 ✅ — Schema port (SQLAlchemy → Supabase numbered migrations)

- [x] Author `002_initial_schema.sql` (13 physical tables — 11 domain-aggregates per §5 mapping, with `appointment_requests` + `appointment_request_services` split out as their own physical tables to preserve source's relational shape; tool_call_audits ported via canonical seed template at `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`).
- [x] Author `003_rls.sql` (admin SSO via `noctus_role = 'platform_admin'` OR `media_scheduling_admin = true` JWT claim; worker/webhook paths use `service_role` and bypass RLS automatically — no `TO service_role` policies needed).
- [x] Author `004_indexes_and_fks.sql` (FKs landed inline in 002 to avoid two-pass resolution; this file ships the secondary indexes the source SQLAlchemy models marked `index=True` plus the canonical seed-template indexes for tool_call_audits).
- [x] Author `005_seed_data.sql` (4 service_types + 4 representative condominiums — names + lat/lon mirror source `scripts/seeds/mock_data.sql` so the seed scheduling/maps adapters' fixtures align).
- [x] Mirror via Supabase MCP `apply_migration` — 5 successful applies (`001_seed` + `002_initial_schema` + `003_rls` + `004_indexes_and_fks` + `005_seed_data`). Confirmed via `list_tables`: 15 tables in `media_scheduling` (13 domain + status_pagina + invitations); all RLS-enabled; `condominiums.rows = 4`, `service_types.rows = 4`.
- [x] **Real-data migration consideration** — DEFERRED to a future follow-up project (`media-scheduling-real-data-migration`). Phase 2 ships canonical seed data only; the real production WhatsApp ↔ OpenAI history + real condominium/property catalog port is a green-bar-after-Phase-6 task and out of scope here.

**Improvements:**
- **Migration filename slip — `001_seed.sql` already existed from Phase 1 scaffold.** The Phase 2 spec named files `001_..` through `004_..`; the engineer renumbered to `002..005` (append-only — never rewrite a committed migration). The slip is in the spec, not the execution. **Defer**: update PROJECT-TEMPLATE.md / `scaffold_product` doc so Phase-2 spec authors know the scaffold consumes `001_seed.sql`. Surface in findings.md L#-next; methodology candidate (NOT in this commit per the architect's collision-risk discipline).
- **PROJECT.md §5 mapping says `Route` → `routes`; source SQLAlchemy `__tablename__` is `route_groups`.** Kept `route_groups` to preserve `appointments.route_group_id` FK target name. **Defer**: fix mapping table when Phase 7 closes the project (PROJECT.md edit). Cataloged here so it survives.
- **`001_seed.sql` was authored in Phase 1 but never mirrored to live Supabase** — the schema didn't exist until Phase 2 mirrored 001 as the prerequisite for 002+. **Methodology improvement**: scaffold_product should optionally apply 001_seed.sql immediately so Phase 2 starts on a non-empty schema. Same defer-to-Phase-7 treatment.
- **`appointment_request_services` policy uses inline JWT predicate, not the parent-table-subquery shape** the mailing reference uses (`list_id IN (SELECT id FROM lists WHERE …)`). Reason: the admin gate is uniform across the whole product (no per-row owner discrimination on this assoc table), so the parent-table subquery would add cost without gating anything new. **Triage**: accept-with-rationale; cataloged here.
- **Canonical helpers in `noctusai_lib.domain.sql_templates` were used as REFERENCE shapes, not invoked at authoring time.** The DDL in 002 matches the helpers' output exactly but was hand-typed. **Future opportunity**: a `noctus.dev.scaffold_migration` MCP tool could generate a 002-shape file from `(schema, [(table, columns)])` using the helpers. Defer — surface in findings.md as a missed MCP-first opportunity.
- **Source SQLAlchemy `ToolCallAudit` had `arguments_json` / `result_json` as TEXT.** Ported to JSONB per the seed template (better for query, matches `AuditRecord.arguments` writer semantics). One small data-shape divergence from source — surfaced here so the Phase 6 test port catches any consumer assuming TEXT. Triage: refactor (already applied — this IS the refactor), no follow-up needed.

### Phase 3 ✅ — Backend: WAHA webhook + buffer + worker via seed

- [x] `routers/webhooks.py` — POST `/webhooks/waha`: HMAC verify (seed `webhook_endpoint(scheme="sha256_hex", signature_header="X-Webhook-Hmac-SHA256", bypass_when_unset=True)`) → `parse_waha_inbound_message(...)` → LID-aware admin lookup → `ConversationBufferService.buffer_inbound(...)`. Returns `{accepted|rejected|ignored}` per source semantics.
- [x] `workers/conversation_worker.py` — instantiate seed `ConversationWorker(buffer_reader=ConversationBufferService(...), processor=...)`. Processor wires `LLMDispatcher(client=OpenAI(), model=settings.openai_chat_model)` with `memory_to_chat_messages(memory)`, 3 placeholder tool descriptions (lookup_property / propose_appointment / confirm_appointment), and an audit-adapter bridging `(ToolCall, ToolResult) → AuditRecord`. Run on a daemon thread via `worker_lifecycle()` (FastAPI `lifespan_startup`).
- [x] `services/lid_auth.py` — product-side LID-aware first-inbound (`LidAuthService` reading `linked_identity` then phone fallback then opportunistic capture; pending-LID parking via `capture_pending_lid`). **Accept-with-rationale**: WhatsApp-specific identity quirk, channel-neutral seed stays clean; promote to seed if N=2+ products surface the same shape.
- [x] `services/audit_hook.py` — wraps `make_audit_writer(db, ToolCallAudit)` with lazy SQLAlchemy session factory (`postgres_url` unset → noop writer with debug log; supabase admin client remains the primary data path). 7 ORM models added under `app/models/` to satisfy seed `make_audit_writer(table_class)` shape.
- [x] `routers/oauth.py` — `/oauth/google/{init,callback}` (public router; init shipped as both GET-redirect AND POST-returns-URL per architect spec) + `/api/oauth/google/status` (admin router; `useOAuthStatus()` consumer).
- [x] `routers/authorized_users.py` — admin CRUD on `authorized_users` (5 endpoints; `is_active`↔`active` and phone normalization on the wire boundary).
- [x] `routers/appointments.py` — admin list (filters: start_date / end_date / status / condominium_id) + detail; `start_at`/`end_at`↔`starts_at`/`ends_at` wire-shape translation.
- [x] `routers/condominiums.py` — read-only list (powers the appointments-filter dropdown).
- [x] `app/main.py` — `routers=[...]` wired with all five product routers + oauth_router exposes both `public_router` and `admin_router`; `lifespan_startup=worker_lifecycle`.
- [x] `app/config.py` — `SeedSettings` extended with redis_url, waha_*, openai_chat_model, google_oauth_*, conversation_*, postgres_url. Defaults are empty strings so `from app.main import app` succeeds in unconfigured envs.
- [x] `requirements.txt` — added `sqlalchemy>=2.0.0`, `psycopg2-binary>=2.9.0`, `openai>=1.40.0` (audit-hook + LLMDispatcher consumers).
- [x] **Smoke test** — `from app.main import app; print('app loads OK')` → `app loads OK` ✓; `app.routes` enumeration confirms all expected paths registered (15 product routes + 8 standard).

**Improvements:**
- **Frontend wire-shape drift (Phase 5 hooks vs schema)** — `useAppointments.ts` references `starts_at`/`ends_at` while DB has `start_at`/`end_at`; `useAuthorizedUsers.ts` references `is_active` and a non-schema `notes` field. Phase 3 routers translate at the boundary (live applied). **Defer**: Phase 6 alignment pass — pick one source of truth (rename hook fields OR rename DB columns) so future phases don't carry the translation tax.
- **OAuth init shape mismatch (architect-spec POST vs frontend-hook GET)** — architect spec says `POST /oauth/google/init`; frontend hook does `window.location.href = '/oauth/google/init'` (which is GET-only). Phase 3 ships BOTH (GET → 302 to Google; POST → JSON `{authorize_url}`) so neither side breaks. **Defer**: Phase 6 should choose one and remove the other (recommend keeping the GET browser-redirect since it's the simpler UX).
- **PROJECT.md §6 Phase 3 spec said `standard_routers=[..., 'webhooks', 'oauth', 'authorized_users', 'appointments', 'condominiums']`** — but `standard_routers` is a seed-managed registry (`{'health','notificacoes','team','llm','ai_outputs','ai_feedback'}`) per `seed/framework/backend/noctusai_seed/routers.py:240`. Used `routers=[...]` (mailing pattern) for product-specific routers; standard_routers stays `["health","notificacoes","team"]`. **Spec wording slip, not implementation slip.** Defer: tighten spec language at Phase 7.
- **Audit-writer SQLAlchemy session is per-call, not request-scoped.** Each tool dispatch opens + closes its own session. Fine for low-volume audit (one row per tool call), but if Phase 6 stress-tests show pool exhaustion under burst, switch to a session-scoped FastAPI dependency. **Triage**: accept-with-rationale (best-effort audit; per-call lifecycle isolates failures).
- **OpenAI client constructed at worker-build time** — if `OPENAI_API_KEY` env is missing the client construction logs an exception and substitutes a sentinel that raises on first use. Per-conversation try/except in the processor catches it. **Triage**: refactor opportunity — defer to Phase 4 (Engineer D may already need a different OpenAI-client lifecycle for tool handlers).
- **Worker uses `threading.Thread(daemon=True)`, not asyncio.** Seed `ConversationWorker.run_forever()` is a blocking `time.sleep`-based loop; thread keeps the FastAPI event loop responsive. Methodology question for Phase 7: should the seed ship an async-flavored `ConversationWorker` so consumers can use `asyncio.create_task` instead? **Triage**: accept; surface to architect for Phase 7 absorption decision.
- **Webhook fallback to `make_fake_redis_client()` when `REDIS_URL` unset** — the webhook STILL accepts + buffers, but cross-process the worker won't see those messages (different fake-redis instance). Logs WARNING explaining the loss. Acceptable for unconfigured-dev; wrong for any env where the webhook actually fires. **Defer**: Phase 6 deploy guide should document the REDIS_URL requirement loudly.

*Phase proposal:* none filed — improvements are scoped enough to live as PROJECT.md notes; the spec-wording slip + Phase 6 alignment items are cataloged here for the architect's pickup at next-phase merge.

### Phase 4 ✅ — Backend: scheduling engine + Calendar/Maps via seed

- [x] `services/scheduling_adapters.py` — `CondoTravelLookup` (TravelLookup Protocol impl wrapping `RoutingLookup`) + `make_scheduling_engine(rules, routing_lookup)` factory composing seed `SchedulingEngine` with `DefaultConflict` + `DefaultScorer` (source repo's verbatim `_is_valid` / `_score` already encoded by the seed defaults; no real-estate-specific Conflict/Scorer needed today).
- [x] `services/condominium_travel.py` — `default_scheduling_rules(timezone_name)` builds a `SchedulingRules` matching source defaults (90/60/10 min); `same_condominium_duration_minutes()` flat constant today with extension hooks for future per-condo overrides.
- [x] `services/crew_assignment.py` — `pick_crew_for_services(supabase, services)` ports source algorithm verbatim (active media_crew with skill superset; lowest-id deterministic tie-break) onto Supabase client (this product's DB layer choice — not SQLAlchemy).
- [x] `services/calendar_writer.py` — `OAuthCredentialResolver` reads `media_scheduling.oauth_credentials` (single-tenant `provider='google', account_email=tenant_account_email`); `CalendarWriter.create_event/delete_event` wraps seed `get_calendar_adapter(resolver=, tenant_id=org_id)`; `build_event_input(...)` centralizes the real-estate event-mapping convention.
- [x] `services/routing_lookup.py` — `RoutingLookup` owns the `condo_id → Coordinates` mapping (per `KB § PATTERNS/scheduling-seed.md`), wraps seed `get_routing_adapter(api_key=)`; in-instance coord cache; conservative 30-min fallback when coords missing OR adapter raises.
- [x] `services/scheduling_tools.py` — 5 `SchedulingToolHandler` impls (`ProposeAppointment` / `ConfirmAppointment` / `CancelAppointment` / `FindAuthorizedUser` / `LookupProperty`), each carrying `name` / `description` / `parameters` / `__call__(args, context) -> ToolResult`. **Integration point exported**: `register_scheduling_tools(dispatcher: LLMDispatcher, context_provider: Callable[[], ToolContext] | None = None) -> None` — attaches `dispatcher.tool_payload`, `dispatcher.tool_handler`, `dispatcher.tool_registry` (shape Engineer C consumes from worker).
- [x] `app/models/` — minimal Pydantic row shapes (`AuthorizedUser`, `Condominium`, `Property`, `ServiceType`, `CrewSkill`, `RouteGroup`, `OAuthCredential`, `Appointment`) — only the columns Phase 4 services touch; merge will dedupe with Engineer C's models.
- [x] **Smoke test green** — `python -c "from app.services.scheduling_adapters import make_scheduling_engine; from app.services.scheduling_tools import register_scheduling_tools; print('imports OK')"` → `imports OK`.
- [x] **Bonus unit tests** — `tests/services/test_scheduling_tools.py` (2 tests): (a) `propose_appointment` against a `StaticRoutingAdapter`-backed `RoutingLookup` returns slots sorted by `(score, start_at)`; (b) `register_scheduling_tools` without context_provider exposes the OpenAI tools payload AND a refusing handler. Full backend suite: 33/33 green.

**Improvements:**
- **Persistent travel-time cache** — the spec mentions caching travel times into `route_groups`, but `route_groups` is the same-day route-plan table, not a generic origin/dest cache. A persistent cache would need a dedicated table (e.g. `travel_time_cache(origin_condo_id, dest_condo_id, minutes, fetched_at)`). Today caching is per-`RoutingLookup`-instance only (fresh per scheduling pass). **Defer**: `media-scheduling-travel-cache` follow-up project; methodology candidate too (the seed `google_maps` could optionally ship a `CachedRoutingAdapter` that wraps any other adapter — same shape as the buffer's `RedisBufferClient` Protocol).
- **`register_scheduling_tools` mutates dispatcher attributes** (`dispatcher.tool_payload`, `dispatcher.tool_handler`, `dispatcher.tool_registry`). The seed `LLMDispatcher` uses per-call `tool_handler=` injection, NOT a registered-handler model. Storing them on the instance keeps Engineer C's worker free of plumbing AND preserves the seed's per-call seam (the worker can still pass them explicitly). **Triage**: accept-with-rationale today; if a 2nd product wants the same registry shape, the registry concept (handler list + OpenAI payload builder + dispatcher-handler closure) belongs in the seed (`noctusai_lib.domain.chatbot.tool_registry`?). Surface in findings.md as a missed seed surface.
- **`unauthorized_user` check on `confirm`/`cancel` reads `context.caller_user_id`** rather than re-validating against the DB. The worker (Engineer C) is responsible for resolving `find_authorized_user` BEFORE invoking confirm/cancel. Defensive double-check returns `unauthorized_user` if the worker doesn't. **Document in Engineer C's worker integration notes**: confirm/cancel handlers need `caller_user_id` populated.
- **Source repo had `appointment_request_audit` (`record_proposal` / `record_confirmation`)** — not ported in this phase. The intent is replaced by the seed `tool_call_audit` pattern (Phase 3 wires `audit_writer` via `noctusai_lib.domain.ai.tool_audit.make_audit_writer`); the per-request audit table the source maintained is functionally subsumed. **Triage**: accept-with-rationale; if the admin UI needs per-request analytics distinct from per-call audits, file a follow-up.
- **No SQLAlchemy ORM in this product** (the backend uses the Supabase client). Every service module that historically used `db.query(...)` was rewritten as `supabase.schema('media_scheduling').table('...').select(...).execute()`. The cost is verbose call sites; the win is full alignment with how the rest of the product (and Engineer C's admin routers / worker) already talks to Supabase. **Document in `KB § backend/` for media-scheduling**: this product is fully Supabase-client-native (no SQLAlchemy) — different from mailing.
- **`appointment_requests` table is NOT touched by Phase 4 handlers** — the source repo wrote a row per propose / confirm cycle. Today the candidate-list response carries the propose-side context implicitly via the OpenAI tool-call audit (Phase 3 audit_writer), so no separate table write is needed. If admin reporting wants per-propose tracking, the Phase 7 audit can re-introduce it. **Triage**: accept-with-rationale; cataloged in this Improvements block.

*Phase proposal:* none filed (improvements bundle small + cross-cutting; persistent-travel-cache + chatbot-tool-registry-seed are genuinely cross-cutting and deserve their own follow-up projects, not per-phase proposals).

### Phase 5 ✅ — Frontend: thin admin via `createProductApp()`

- [x] `pages/AuthorizedUsersPage.tsx` — CRUD on `authorized_users` (WhatsApp-authorized phones, NOT SSO users).
- [x] `pages/AppointmentsPage.tsx` — list + filter (date range, status, condominium).
- [x] `pages/OAuthStatusPage.tsx` — Google Calendar OAuth status + reconnect.
- [x] All hooks in dedicated files (`useAuthorizedUsers.ts`, `useAppointments.ts`, `useOAuthStatus.ts`).
- [x] Wired into `createProductApp({routes,...})` + `NAV_GROUPS` + `NAV_FALLBACK` (icons: `UserCheck`, `Calendar`, `Link2`).
- [x] `npx vite build` green — 1772 modules transformed, all 3 lazy-loaded chunks emitted (AuthorizedUsersPage 10.33 kB, AppointmentsPage 7.29 kB, OAuthStatusPage 4.67 kB).
- Note: `authProvider=seed_sso` already wired upstream by `createProductApp` defaults via `infra.appConfig` — no Phase-5 change needed; `useAuthStore()` gates queries on the user being signed in.

**Improvements:**
- API endpoint paths in hooks are placeholders (`/api/authorized-users`, `/api/appointments`, `/api/condominiums`, `/api/oauth/google/status`, `/oauth/google/init`) marked `// TODO Phase 3 — confirm endpoint path`. Phase 3 backend engineer must align to these OR the hooks get a follow-up sweep.
- `seed/lib/frontend` had no `node_modules` — every product build failed at rollup-resolving `clsx` from `seed/lib/frontend/src/utils.ts`. Workaround: ran `npm install` in `seed/lib/frontend/` so peer deps (clsx / tailwind-merge / etc.) resolve. **Better fix (defer to Phase 7 / shared-library follow-up project):** the shared `vite.config.factory.ts` should add `clsx`, `tailwind-merge`, `class-variance-authority` to `FRAMEWORK_DEPS` (so they `dedupe` to product node_modules) — currently only react/react-dom/router/query/zustand/sonner/lucide/radix/supabase are listed. Same surface as the worktree-venv-isolation Phase 0.5 finding (a shared-config gap that hits every product).
- `package.json` name field is the literal `"seed-frontend"` (carried over from scaffold); naming is global to all scaffolded products. Defer to Phase 7 cleanup or future `scaffold_product` improvement.
- AppointmentsPage filter for "condominium" relies on `useCondominiumOptions()` hook (also TODO-Phase 3). Could be inlined as a free-text filter as a fallback if the dropdown endpoint isn't ready by Phase 6 verification.

### Phase 6 — Test port + green-bar verification

- [ ] Port source unit tests.
- [ ] Add seed-consumption integration tests.
- [ ] `cd products/media-scheduling/backend && pytest` → green.
- [ ] `cd products/media-scheduling/frontend && npx vite build` → green.
- [ ] `cd mcp/noctusai && pytest tests/` → green.

### Phase 7 — Pattern compliance sweep + close

- [ ] `noctus.dev.scan_cross_product_helpers` → 0 findings (or each cataloged).
- [ ] `noctus.dev.scan_service_line_recurrence` → 0 findings.
- [ ] `noctus.dev.scan_recurrence` → 0 findings.
- [ ] `noctus.dev.validate` → seed-compliance score.
- [ ] `noctus.dev.review_session` → body-free regression check.
- [ ] Phase-learning log via `noctus.dev.phase_learning_log` for every phase.
- [ ] `MEDIA-SCHEDULING-PORT-LOG.md` final reflections.
- [ ] `findings.md` synthesis at close.
- [ ] KB updates landed (`02-LANDSCAPE.md`, `accept-with-rationale.md` LID entry).
- [ ] Project archived via `noctus.dev.archive`.

---

## 7. Open questions

1. **LID-aware first-inbound auth — generalizes?** — needs answer before Phase 3. Recommendation: catalog as accept-with-rationale; if N=2+ WhatsApp products later, absorb into seed.
2. **Source repo's PostgreSQL profile — keep parity?** — Phase 2 decision. Recommendation: NO — Supabase replaces it.
3. **Frontend OAuth flow hosting** — Phase 5. Recommendation: backend hosts callback; frontend initiates redirect.
4. **Conversation summary cadence** — Phase 3 discovery; check seed `chatbot.worker` defaults.
5. **Real-data migration during Phase 2** — preserve real conversation history or start clean? Phase 2 entry-point decision.

---

## 8. Dependencies & blockers

- **None blocking** — Phase 0 confirmed all seed surfaces runtime-ready in canonical shape (after Phase 0.5 closes the three gaps).
- **Supabase MCP** — required for Phase 2 migration mirror. In keep-list.
- **Source repo read access** — confirmed.

---

## 9. Success criteria

- `noctus.dev.list_products` returns `media-scheduling`.
- `noctus.dev.validate` scores `media-scheduling` ≥ median of existing products.
- All test layers green (backend pytest + frontend vite build + MCP pytest).
- Absorption-search trio returns 0 findings.
- `MEDIA-SCHEDULING-PORT-LOG.md` + `findings.md` populated through final reflections.
- Schema in Supabase `media_scheduling` mirrors numbered migrations exactly.
- LID-auth carve-out documented in `KB § PATTERNS/accept-with-rationale.md`.

---

## 10. How to use this plan

- Single source of truth for progress.
- **Per-phase local commits** (collision learning — was originally project-end-only, that cadence proved fragile in parallel-active-work environments).
- Phase-by-phase by default; pause for user "continue" between phases.
- Capture improvements live; synthesize one phase proposal at end of each phase.
- **Branch:** `media-scheduling-port-resume`. **Worktree:** `noctusai-worktrees/media-scheduling-port-resume/`.

### Copy-paste commands (worktree-relative)

```bash
# Phase 0.5 tests
cd /Users/rapha/Documents/repository/NoctusAI/noctusai-worktrees/media-scheduling-port-resume/seed/lib/backend && pip install -e . && pytest tests/integrations/whatsapp/test_fake_adapter.py tests/integrations/test_redis.py tests/domain/chatbot/test_in_memory_buffer.py -v

# Per-phase commit
git add -A  # only after verifying staged files via git diff --cached --name-only
git commit -m "phase(media-scheduling-port-resume): Phase 0.5 ✅ — seed Fake+Real backfill (G1-G4)"

# Phase 1 scaffold (via MCP)
# noctus.dev.scaffold_product(name='Media Scheduling', slug='media-scheduling', schema='media_scheduling', icon='Calendar', backend_port=8096, frontend_port=8130)

# Phase 7 close (via MCP)
# noctus.dev.archive(path='projects/media-scheduling-port/')
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial plan drafted (original session, lost in collision) | claude-opus-4-7 |
| 2026-05-04 | Re-created in dedicated worktree `noctusai-worktrees/media-scheduling-port-resume/` post-collision; Phase 0 results preserved; Phase 0.5 in re-execution; per-phase commit cadence adopted as collision learning; new Q5 added (real-data migration during Phase 2) | claude-opus-4-7 |
| 2026-05-04 | Phase 0.5 ✅ — G1-G4 backfill landed (commit `2defcfe`, 88 tests green). Improvements: (a) retrofit @runtime_checkable on RedisBufferClient — defer follow-up sweep for any other lacking-decorator seed Protocols; (b) worktree-venv-isolation gap surfaced (hook fallback to system python3 in fresh worktree) — defer follow-up project. Phase learnings logged via `noctus.dev.phase_learning_log` (3 entries: technical / methodology / process). | claude-opus-4-7 |
| 2026-05-04 | Phase 1 ✅ — products/media-scheduling/ scaffolded (41 files, manually since MCP scaffold_product points at main worktree). backend/app/main.py + frontend/src/App.tsx confirmed using create_product_app() / createProductApp(). Improvements: scaffold.py extension filter misses .env.example (filed as `scaffold-tool-extension-coverage` follow-up), MCP scaffold_product needs per-call workspace override for multi-worktree environments (filed as `mcp-workspace-per-call-override` follow-up). LANDSCAPE.md + start.sh + vite.config.factory.ts wiring deferred to Phase 7 close (collision-risk on shared tracked files). | claude-opus-4-7 |
| 2026-05-04 | Phase 2 ✅ — Schema port landed in dedicated worktree `media-scheduling-phase-2-schema` (Engineer A, parallel-dispatched alongside Phase 5 per architect-engineer methodology). 4 numbered migration files authored (`002_initial_schema.sql`, `003_rls.sql`, `004_indexes_and_fks.sql`, `005_seed_data.sql`); renumbered from spec's 001-004 because Phase 1's `scaffold_product` already shipped `001_seed.sql` (append-only migration discipline). 13 physical tables ported from source SQLAlchemy models; tool_call_audits via canonical seed template (with TEXT→JSONB upgrade); RLS = admin SSO via `noctus_role`/`media_scheduling_admin` JWT claim, worker writes via service_role. All 5 migrations mirrored via Supabase MCP `apply_migration` (`{"success":true}` × 5); `list_tables` confirms 15 tables in `media_scheduling` schema (13 domain + status_pagina + invitations) all RLS-enabled. Real-data migration deferred to follow-up project. Improvements block surfaces: filename-slip in spec (defer to PROJECT-TEMPLATE update); §5 mapping `Route → routes` should be `route_groups`; `001_seed.sql` was authored Phase 1 but never mirrored (scaffold_product methodology gap); MCP-first opportunity for `noctus.dev.scaffold_migration`. | Engineer A (subagent of claude-opus-4-7) |
| 2026-05-04 | Phase 5 ✅ — Frontend thin admin landed in dedicated worktree `media-scheduling-phase-5-frontend` (Engineer B, parallel-dispatched alongside Phase 2). 3 pages + 3 hooks + App.tsx wiring. `npx vite build` green (1772 modules; AuthorizedUsersPage 10.33 kB / AppointmentsPage 7.29 kB / OAuthStatusPage 4.67 kB lazy chunks). Hooks use placeholder API paths flagged `// TODO Phase 3` — Phase 3 engineer must honor or surface mismatches: `/api/authorized-users`, `/api/appointments`, `/api/condominiums`, `/api/oauth/google/status`, `/oauth/google/init`. Improvements surfaced: (a) `vite.config.factory.ts` missing `clsx` / `tailwind-merge` / `class-variance-authority` in `FRAMEWORK_DEPS` — shared-config gap, same shape as worktree-venv-isolation; defer to Phase 7 / follow-up project; (b) scaffold-generated `package.json` name is literal `"seed-frontend"`; (c) `useCondominiumOptions()` depends on `/api/condominiums` (Phase 3); (d) authProvider=seed_sso ALREADY wired via `infra.appConfig` in `createProductApp` defaults — no manual wiring needed. | Engineer B (subagent of claude-opus-4-7) |
| 2026-05-04 | Phase 3 ✅ — Backend WAHA + buffer + worker landed in dedicated worktree `media-scheduling-phase-3-backend-waha` (Engineer C, parallel-dispatched alongside Phase 4). Files created: `app/routers/{webhooks,oauth,authorized_users,appointments,condominiums}.py` (5 routers; 12 endpoints honoring Phase 5 frontend contract); `app/services/{lid_auth,audit_hook}.py`; `app/workers/conversation_worker.py` (daemon-thread `ConversationWorker` consuming seed primitives + 3-tool placeholder dispatcher + `register_scheduling_tools` graceful-degrade hook for Engineer D); `app/models/*.py` (7 SQLAlchemy ORM models for the seed `make_audit_writer(db, table_class)` shape); `app/main.py` extended with `routers=[...]` + `lifespan_startup=worker_lifecycle`; `app/config.py` extended with WAHA / Redis / OpenAI / Google-OAuth / Postgres URL fields (all empty-string defaults). Smoke test green: `from app.main import app; print('app loads OK')` → `app loads OK`. All Phase 5 frontend hook URLs honored exactly: `GET /api/authorized-users` (+ POST/GET/PATCH/DELETE), `GET /api/appointments` (+ /{id}, filters), `GET /api/condominiums`, `GET /api/oauth/google/status`, `POST /oauth/google/init` (+ GET-redirect for browser), `GET /oauth/google/callback`, `POST /webhooks/waha`. Improvements surfaced (per-phase block above): wire-shape drift (`starts_at` vs `start_at`; `is_active` vs `active`; non-schema `notes`) translated at boundary — defer Phase 6 alignment; OAuth init shipped as both GET+POST so neither side breaks; spec-wording slip (architect said `standard_routers=[...]` but those are seed-managed names — used `routers=[...]` instead per mailing reference); audit-writer per-call session lifecycle (accept-with-rationale; revisit if pool-exhaustion); worker uses threading.Thread (architect Q for Phase 7: should seed ship async worker?); webhook FakeRedis fallback when REDIS_URL unset (cross-process worker invisible — document loudly in Phase 6 deploy guide). LID-auth product-side accept-with-rationale logged. | Engineer C (subagent of claude-opus-4-7) |
| 2026-05-04 | Phase 4 ✅ — Backend scheduling adapters + Calendar/Maps + LLM tool handlers landed in dedicated worktree `media-scheduling-phase-4-backend-scheduling` (Engineer D, parallel-dispatched alongside Engineer C's Phase 3). 6 service modules + 8 minimal Pydantic models + 2 unit tests. **Integration contract for Engineer C**: `from app.services.scheduling_tools import register_scheduling_tools; register_scheduling_tools(dispatcher, context_provider=lambda: ToolContext(...))` — attaches `dispatcher.tool_payload` (OpenAI tools=[...]), `dispatcher.tool_handler` (Callable[[ToolCall], ToolResult]), and `dispatcher.tool_registry`. Five tools shipped: `propose_appointment`, `confirm_appointment`, `cancel_appointment`, `find_authorized_user`, `lookup_property`. Source-repo `_is_valid` / `_score` already encoded by seed `DefaultConflict` / `DefaultScorer` so no real-estate Conflict/Scorer custom subclasses needed. Smoke test (architect-spec'd) + 2 unit tests + full backend pytest = 33/33 green. Improvements surfaced: persistent-travel-cache (defer follow-up — `route_groups` ≠ generic cache); registry-on-dispatcher mutation (accept-with-rationale; promote to seed if N=2+); confirm/cancel relies on worker pre-resolving `caller_user_id`; `appointment_requests` table not touched (audit pattern subsumes); product is Supabase-client-native (no SQLAlchemy — diverges from mailing reference). Engineer C's webhook+worker import remains stable contract. | Engineer D (subagent of claude-opus-4-7) |
| 2026-05-04 | Architect resolution at Phase 3+4 merge: model files conflict on add/add for `appointment.py` / `authorized_user.py` / `condominium.py` / `oauth_credential.py` (Engineer C SQLAlchemy ORM vs Engineer D Pydantic). Resolved by keeping Engineer D's Pydantic for those four (Supabase-client-native is the actual product approach per §2; Engineer C's own docstring acknowledged ORM models were primarily for the audit-writer contract). Kept Engineer C's `ToolCallAudit` + `ConversationSummary` + `PendingChatIdentity` ORM (only `ToolCallAudit` has a current consumer; the other two are speculative ORM that coexists harmlessly with `Base/SCHEMA`). New hybrid `app/models/__init__.py` documents the layout. PROJECT.md status + change-log auto-conflicts resolved by concat (KB-doc heuristic). | claude-opus-4-7 (architect) |
