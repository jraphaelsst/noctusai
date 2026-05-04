# Media Scheduling — Port from external repo to noc product (resumed)

- **Created:** 2026-05-03 (original) / 2026-05-04 (resumed in dedicated worktree)
- **Last updated:** 2026-05-04
- **Status:** Phase 0 ✅ + Phase 0.5 ✅ + Phase 1 ✅ + Phase 2 ✅ → Phase 3 ready
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

### Phase 1 — Scaffold `products/media-scheduling/`

- [ ] `noctus.dev.scaffold_product(name='Media Scheduling', slug='media-scheduling', schema='media_scheduling', icon='Calendar', backend_port=8096, frontend_port=8130)`.
- [ ] Confirm `products/media-scheduling/{backend, frontend, projects, proposals, README.md, MASTER-PROMPT.md}` landed.
- [ ] Confirm backend `app.py` calls `create_product_app(...)`; frontend `app.tsx` calls `createProductApp(...)`.
- [ ] Update `KB § 02-LANDSCAPE.md`.

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

### Phase 3 — Backend: WAHA webhook + buffer + worker via seed

- [ ] `routers/webhooks.py` — POST `/webhooks/waha`: HMAC verify → seed parser → seed buffer.
- [ ] `workers/conversation_worker.py` — consumes seed `chatbot.worker`; LLM-dispatcher wired to OpenAI structured outputs.
- [ ] LID-aware first-inbound capture stays product-side; accept-with-rationale entry filed.
- [ ] Tool-call audit via seed pattern.
- [ ] `routers/oauth.py` — Google Calendar OAuth flow → `oauth_credentials`.

### Phase 4 — Backend: scheduling engine + Calendar/Maps via seed

- [ ] `services/scheduling_adapters.py` — product-side `Conflict` / `Scorer` / `TravelLookup` adapters.
- [ ] `services/condominium_travel.py` — same-condominium duration logic; pluggable into `TravelLookup`.
- [ ] `services/crew_assignment.py` — crew-skill matching; pluggable into `Scorer`.
- [ ] Calendar writer via seed `google_calendar`.
- [ ] Travel-time fetch via seed `google_maps` (cached into `routes` table).

### Phase 5 — Frontend: thin admin via `createProductApp()`

- [ ] `pages/AuthorizedUsersPage.tsx` — CRUD on `authorized_users`.
- [ ] `pages/AppointmentsPage.tsx` — list + filter.
- [ ] `pages/OAuthStatusPage.tsx` — Google Calendar OAuth status + reconnect.
- [ ] All hooks in dedicated files.
- [ ] Wire `authProvider=seed_sso`.

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
| 2026-05-04 | Phase 2 ✅ — Schema port landed in dedicated worktree `media-scheduling-phase-2-schema` (Engineer A). 4 numbered migration files authored (`002_initial_schema.sql`, `003_rls.sql`, `004_indexes_and_fks.sql`, `005_seed_data.sql`); renumbered from spec's 001-004 because Phase 1's `scaffold_product` already shipped `001_seed.sql` (append-only migration discipline). 13 physical tables ported from source SQLAlchemy models; tool_call_audits via canonical seed template (with TEXT→JSONB upgrade); RLS = admin SSO via `noctus_role`/`media_scheduling_admin` JWT claim, worker writes via service_role. All 5 migrations mirrored via Supabase MCP `apply_migration` (`{"success":true}` × 5); `list_tables` confirms 15 tables in `media_scheduling` schema (13 domain + status_pagina + invitations) all RLS-enabled. Real-data migration deferred to follow-up project. Improvements block surfaces: filename-slip in spec (defer to PROJECT-TEMPLATE update); §5 mapping `Route → routes` should be `route_groups`; `001_seed.sql` was authored Phase 1 but never mirrored (scaffold_product methodology gap); MCP-first opportunity for `noctus.dev.scaffold_migration`. | claude-opus-4-7 (Engineer A) |
