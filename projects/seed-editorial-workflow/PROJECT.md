# seed-editorial-workflow — Project Document

- **Created:** 2026-10-04
- **Last updated:** 2026-10-04
- **Status:** Phase 0 ✅ · Phase 1 ✅ (E1+E2 on `feat/editorial-e1-e2`, awaiting integrate) → Phase 2 ready · 🅿️ one owner decision open (§7)
- **Owner / stakeholders:** João (owner) · Mônica Tangerino (first editor) · first consumer: Nós no Limiar content (activities + AI knowledge base; spec §22)
- **Related docs:** `projects/platform-admin-mfa/PROJECT.md` (sibling; editorial admins need MFA) · limiar-app `docs/plan/fase-1-mvp.md` §6 (b) · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `KB § PATTERNS/architect/project-execution.md` (recurrence rule)
- **Project slug:** `seed-editorial-workflow` (seed organ + first consumer in `agents` ⇒ `projects/`)

---

## 1. Context & Purpose

Nós no Limiar's spec §22 requires content states rascunho → revisão editorial → revisão de segurança/fonte →
publicado → arquivado, a record of who approved each change, and no AI publishing alone. That workflow exists
nowhere on the platform, while "draft → publish" already exists in three ad-hoc shapes (agents definition
versions, agents knowledge store, igig pauta approval). Recurrence rule: the 3rd+ instance MUST formalize ⇒ one
seed organ, consumed first by the agents knowledge store (which will hold the Nós no Limiar activities and AI
knowledge documents).

## 2. Confirmed constraints

- Owner go-ahead 2026-10-04 (Decision Board `nnl-f1-admin-mfa`, option "platform").
- Mônica reviews and approves all Nós no Limiar content (`nnl-f1-editorial`); Claude drafts as `rascunho`
  (`nnl-f1-drafts`).
- Until this ships, Nós no Limiar content stays in git, reviewed by PR (limiar-app decisions log).
- Prod-only fleet: the agents migration must not hide existing knowledge (backfill to `publicado` v1).
- No edits to `products/social-wiring` (peer session).

## 3. Design principles

States are a FIXED code-defined machine (not user-editable rows — the seed pipeline is the wrong base);
per-transition named grants; separation of duties enforced in code AND in the DB; versions immutable, events
append-only; one draft at a time while the published version keeps serving.

## 3a. Seed-first analysis

New seed domain `noctusai_lib/domain/editorial/` (state machine + store Protocol/Fake/Supabase/factory + SQL
template + router factory) and FE organs; grants reuse the existing permissions organ (`require_permission`,
`domain/permissions/repo.py`). Consumers adopt via named seams; no product-local copy.

## 4. Scope

In: E1–E5 below; agents knowledge as pilot consumer. Later (separate phases/projects, by owner call): agents
`agent_versions` (eval gate as a transition guard hook), igig pauta approval (client link as token-actor
transition).

## 4a. Dispatch routing

| Slice | Lens | Files (collision zone) | Parallel with | Prod risk |
|---|---|---|---|---|
| E1 domain state machine + Fake store + tests | backend-engineer | `seed/lib/backend/noctusai_lib/domain/editorial/*` | M*, E2 | none |
| E2 SQL template + Supabase store + guard probes | backend-engineer | `sql_templates.py`, `editorial/store_supabase.py`, `mcp/noctusai/tools/noctus/dev/verify_db_guards.py` | M*, E1 (after the E1 Protocol is fixed) | none |
| E3 router factory | backend-engineer | `editorial/router.py` | E4 | none |
| E4 FE organs (ReviewQueue, EditorialTimeline, VersionDiff) + `organ.yaml` | frontend-engineer | `seed/lib/frontend/src/components/editorial/*` | E3 | none |
| E5 agents migration 018 + store/runtime/importer adoption | backend-engineer | `products/agents/*` | M5 | **high** (retrieval could hide docs — backfill) |

## 5. Architecture (architect review 2026-10-04)

**Existing shapes.** agents definition versions (`products/agents/backend/migrations/012_agent_studio_definitions.sql`:
`rascunho/ativa/substituida`, partial uniques one-draft/one-active, immutability triggers, publish RPC + eval gate
013:337,505, `agent_audit_log` + `publicado_override`) · agents knowledge (013:104-185,
`app/stores/studio_knowledge.py`: only `ativo bool`, append-only `knowledge_revisions`; importer/package sync 017
upsert by `source_sha` ⇒ live immediately) · igig (`products/igig/backend/migrations/017_igig_pipeline.sql`:
approval = pipeline stage `aprovacao_cliente` + `aprovacao.emitido_por`, on the seed `domain/pipeline` — wrong base
here: user-editable stages).

**Design `noctusai_lib/domain/editorial/`.**
- `EditorialWorkflow` config: states `rascunho → revisao_editorial → revisao_seguranca → publicado → arquivado`;
  per-transition grant (`editorial:editar`, `editorial:revisar`, `editorial:revisar_seguranca`,
  `editorial:publicar`); separation of duties (approver ≠ author; security approver ≠ editorial approver of the
  same version). Pure `decide_transition()`.
- `EditorialStore` Protocol + Fake + Supabase + `make_editorial_store(schema)`: item (`state`,
  `published_version_n`), version (immutable: `n`, content JSONB, `content_sha`, `author_id`), event (append-only:
  from/to, `actor_id`, grant, `motivo`, version n).
- `sql_templates.editorial_tables(schema)`: the three tables, write-once/append-only triggers, SECURITY DEFINER
  `editorial_transition()` re-checking legality + separation of duties in the DB; every guard probed by
  `verify_db_guards`.
- Edit-after-publish like `agent_versions`: one draft at a time, published version keeps serving.
- `editorial_router(ctx)` factory (shape of `pipeline_stages_router`): queue by state, item + versions + events,
  new version, transition, diff.
- FE organs `components/editorial/{ReviewQueue,EditorialTimeline,VersionDiff}` (VersionDiff reuses
  `components/markdown`), each with `organ.yaml`.

**Pilot consumer: agents knowledge.** `knowledge_documents.editorial_item_id`; collections get `requer_revisao`;
retrieval reads only the published version; imports into governed collections land as drafts; backfill every
existing document to `publicado` v1 (nothing disappears in prod).

## 6. Implementation phases

### Phase 0 — Audit ✅
- [x] Re-read §5 files at the current tip; confirm the permissions organ API; inventory the knowledge read paths E5 must switch.
  - Knowledge read paths E5 must switch to "published version only": `agents.search_knowledge` (013, filters `d.ativo = true`), `agents.list_knowledge_documents` (013:430), store `get_document` / `get_document_by_slug` / `read_document_part` / `list_documents` (`studio_knowledge.py`), `upsert_document_by_source_sha` (importer + package sync 017 — today live immediately), `studio_knowledge_router.py`. The retrieval SQL joins on `ativo`, so the cheapest switch is a published-version predicate in `search_knowledge`, not a new read path.
**Improvements:** (1) §5's line refs "013:337,505" no longer hold — 012/013/017 contain NO publish RPC; publish is an app-side status flip (`studio_agents_router` + `require_publish_write`) under the `guard_agent_version_immutable` trigger, so "eval gate as a transition guard hook" (§4, later) means a hook in the router/store, not in the DB function. (2) Permissions organ grants are USER-GLOBAL (`public.user_permission_grants(user_id, permission)`, core 046) — no org/product dimension; an `editorial:publicar` holder can publish in every org. E3's router MUST also require org membership + item `org_id` match (the store already filters by org), and E5 should decide whether editor grants need an org-scoped variant. (3) `has_permission` is not callable from the editorial functions without cross-schema coupling, so the DB receives `p_grants` from the service-role caller and re-checks legality + separation of duties only; the grant TRUTH stays with the permissions organ (the router must derive grants server-side, never from the request body).

### Phase 1 — E1 + E2 (domain + store + SQL template; default unused) ✅
- [x] State machine + Fake store + tests (`seed/lib/backend/noctusai_lib/domain/editorial/`, 65 tests); SQL template `sql_templates.editorial_tables(schema)` + `SupabaseEditorialStore`; 23 `verify_db_guards` probes (product `seed-editorial`, each builds the template in a rolled-back scratch schema — template not applied anywhere).
**Improvements:** (1) The spec's four grants vs five states left "who publishes after security sign-off" open: modelled as `approve_security` (sign-off, state unchanged, `revisar_seguranca`) then `publish` (`publicar`, needs the sign-off, publisher != author) — flag to the owner with §7 Q1. (2) Approvals are scoped to (version, review round): a send-back + re-submit clears them. (3) The SQL was validated by `pglast` parse (SQL + every plpgsql body) and by shape tests, NOT executed — no local Postgres/docker was available; the 23 probes are the executable proof and should be run via `noctus.dev.verify_db_guards` before E5 applies a migration. (4) `arquivado` is terminal (no un-archive) — revisit if editors need it. (5) Dead-simple extension point left: `editorial_tables(schema, workflow)` generates `editorial_rules()` from the Python workflow, so a stricter subset never drifts from the DB.

### Phase 2 — E3 + E4 (router factory + FE organs)
- [ ] Router + strict auth tests; organs + organ.yaml.
**Improvements:** NOC-FILL-IMPROVEMENTS

### Phase 3 — E5 agents adoption (needs admin MFA enforce-able for editors) 🅿️ §7 Q1
- [ ] Migration 018 + backfill; retrieval reads published only; importer drafts into governed collections.
**Improvements:** NOC-FILL-IMPROVEMENTS

## 7. Open questions (Decision Board)

1. `nnl-editorial-roles` — Mônica: editorial review + publish · João: security/source review (**recommended**);
   Claude drafts attributed to a "Claude (rascunho)" identity.

## 8. Dependencies & blockers

E5 depends on `platform-admin-mfa` reaching `enforce` capability for the agents product (editors are admins).

## 9. Success criteria

A Nós no Limiar activity drafted by Claude cannot reach the app until an editorial reviewer and a different
security/source reviewer approve and a publisher publishes it; every step is in the event log with actor and
grant; the DB refuses an illegal transition even if the API is bypassed; existing agents knowledge stays served.

## 10. How to use this plan

Phases in order; slices via `noctus.dev.task_branch` off `origin/dev`, pointer project `seed-editorial-workflow`.
Gates: seed lib pytest, agents suite, `verify_db_guards`, MCP tests, `gate_sweep` before integrate.

## 11. Change log

- 2026-10-04 — Filed from the architect design review (owner go-ahead 2026-10-04).
- 2026-10-04 — Phase 0 audit: §5 line refs for the agents publish RPC are stale (none exists; publish is app-side); permissions grants are user-global, not org-scoped (E3 must add org membership; E5 decides on org-scoped grants); DB receives grants from the caller. Phase 1 (E1+E2) built on `feat/editorial-e1-e2`: state machine + Fake/Supabase stores + `editorial_tables` + 23 guard probes.
