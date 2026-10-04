# seed-editorial-workflow — Project Document

- **Created:** 2026-10-04
- **Last updated:** 2026-10-04
- **Status:** Design locked (architect review 2026-10-04) → Phase 1 ready · 🅿️ one owner decision open (§7)
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

### Phase 0 — Audit
- [ ] Re-read §5 files at the current tip; confirm the permissions organ API; inventory the knowledge read paths E5 must switch.
**Improvements:** NOC-FILL-IMPROVEMENTS

### Phase 1 — E1 + E2 (domain + store + SQL template; default unused)
- [ ] State machine + Fake store + tests; SQL template + Supabase store + guard probes.
**Improvements:** NOC-FILL-IMPROVEMENTS

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
