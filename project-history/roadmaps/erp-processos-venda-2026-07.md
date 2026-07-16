# erp-processos-venda-2026-07 — Processos de Venda kanban + canonical KanbanBoard organ

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: user-requested second kanban on ERP — the post-proposal execution pipeline — which surfaced an N=3 kanban recurrence.
> Decision: **promote a canonical `KanbanBoard` organ FIRST, build Processos de Venda on it, repoint erp Funil as pilot; orbity Funil fans out later.**

## Origin

2026-07-16, user (Raphael) asked for a new kanban page on the ERP sidebar under "Funil de Vendas",
called **Processos de Venda**: the continuation of the sales process once a proposal is accepted.
The seam is a **button on the Funil cliente card while it sits in the `proposta` column** — accepting
the proposal moves the deal onto the new board at its first stage.

Scoping the request surfaced a methodology trigger: the ERP Funil board is a hand-rolled `@dnd-kit`
implementation (`pages/Funil.tsx` + `components/clientes/ColunaFunil.tsx` + `ClienteCard.tsx`), and
`products/orbity/frontend/src/pages/Funil.tsx` is an **independent second fork** of the same shape.
A local Processos board would be the **third** — and the DRY recurrence rule (`N=3+ MUST formalize;
shipping the 4th instance is forbidden`) fires. User chose organ-promotion-first over ship-local-and-triage-later.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | **Organ lands + erp Funil repointed green** | `@noctusai/lib` exports `KanbanBoard`; erp Funil imports it; vitest + playwright `funil.spec.ts` green | Processos must be built on the organ, not beside it — otherwise the promotion was theater |
| T2 | **A 4th kanban consumer appears** | any new `dnd-kit` import outside `@noctusai/lib` | The forbidden-4th-instance rule; forces orbity fan-out to complete |
| T3 | **Funil↔Processos handoff needs an audit trail** | user asks "who accepted this proposal and when" | `erp.funil_movimentos` exists but `mover_etapa` never writes to it — a pre-existing gap this roadmap must not silently inherit |

**Today's status**: none fired yet — Phase 1 is the organ promotion itself.

> **Every slice carries TWO recipes, not one.** A *test-recipe* (unit/CI proof, green at the module
> boundary) is **not** a *verify-recipe* (proof against LIVE state — the page renders real rows, the
> drag persists, the button spawns a row). Tests-green ≠ verified-in-production. Fill the Verify
> recipe column for every slice; an empty one is a positive "no live check needed" claim, not a skip.

## Phase 1 — canonical KanbanBoard organ + erp Funil repoint (PLANNED)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P1.1 | Extract `KanbanBoard` / `KanbanColumn` / `KanbanCard` organ | NEW `seed/lib/frontend/src/components/kanban/` + `@noctusai/lib` export | planned | Import from a scratch consumer; drag a card across columns in a browser and see `onMove` fire with correct `(id, fromStage, toStage, index)` |
| P1.2 | Register the organ in the canonical catalog | `noctus.dev.register_organ` + catalog | planned | `noctus.dev.component_list` returns `KanbanBoard`; `check_canonical_organ_consumption` recognizes it |
| P1.3 | Repoint erp Funil onto the organ (pilot #1) | EDIT `products/erp-imobiliario/frontend/src/pages/Funil.tsx`, `components/clientes/ColunaFunil.tsx`, `ClienteCard.tsx` | planned | Load `/funil` against a real ERP backend: columns show real counts + `valorTotal`, drag persists across reload (`POST /api/clientes/{id}/mover-etapa`) |

**Behavior guarantee**: the ERP Funil's runtime behavior does not change — same columns, same drag,
same optimistic update. This is a pure structural repoint. Any visible change is a regression.

**Why ship now**: building Processos on a local fork and promoting later means writing the board
twice and repointing twice. The organ is cheapest before the third consumer exists, not after.

## Phase 2 — Processos de Venda (DEFERRED — fires when T1 ∧ Phase 1.5 landed)

| # | Title | Files | Trigger | Verify recipe (write it now, run it when it ships) |
|---|---|---|---|---|
| P2.1 | Migration: `etapa_processo` enum + `processos_venda` table (FK → `clientes` **+ `negociacoes_venda`**) + `status_pagina` row + index | NEW `products/erp-imobiliario/backend/migrations/0NN_processos_venda.sql` | T1 ∧ P1.5 | Apply to a real DB; `\d erp.processos_venda`; confirm the `status_pagina` row exists (without it the nav item silently never renders) |
| P2.2 | Backend router + DTO service | NEW `backend/app/routers/processos_venda.py`, `app/services/processos_venda_service.py`; EDIT `main.py` `routers=[...]` | T1 ∧ P1.5 | `curl /api/processos-venda` on a live ERP container → real grouped columns, not `[]` |
| P2.3 | Accept-proposal seam | EDIT the negociação router (P1.5) — `POST /{negociacao_id}/aceitar-proposta` | T1 ∧ P1.5 | Accept a proposal on a real negociação in `proposta`; assert exactly one `processos_venda` row spawns at `elaboracao_contrato`, the negociação leaves the Funil board, and a double-click yields ONE row (idempotency) |
| P2.4 | Frontend page on the organ + nav + route | NEW `pages/ProcessosVenda.tsx`, `types/processos.ts`, `lib/etapasProcessoConfig.ts`, `hooks/useProcessos.ts`; EDIT `App.tsx` (nav + route + lazy) | T1 ∧ P1.5 | Page shows real rows; drag persists; sidebar entry renders under Funil de Vendas |
| P2.5 | "Aceitar Proposta" button on the Funil card, `proposta` column only | EDIT the Funil card component (post-P1.5.4 it renders a negociação) | T1 ∧ P1.5 | Click the button on a `proposta` card in a browser → card leaves Funil, appears on Processos. Handler MUST `e.stopPropagation()` — the card body carries dnd-kit drag listeners |
| P2.6 | Tests | NEW `backend/tests/routers/test_processos_venda_router.py`, `frontend/e2e/tests/processos-venda.spec.ts`; EDIT `e2e/tests/sidebar.spec.ts` | T1 ∧ P1.5 | — (this row IS the test-recipe; its verify-recipe is P2.1–P2.5's) |

**Trigger**: T1 (organ green on the Funil pilot) **and** Phase 1.5 landed — `processos_venda.negociacao_venda_id`
has nothing to reference until the entity exists.

**Why not now**: a Processos board written before the organ is the third fork the DRY rule forbids; and
built before Phase 1.5 it would hang off `cliente_id` alone and need re-migrating once negociações exist.

## Phase 3 — orbity Funil fan-out (DEFERRED — fires when T2, or opportunistically)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P3.1 | Repoint orbity Funil onto the organ (pilot #2) | EDIT `products/orbity/frontend/src/pages/Funil.tsx` + its `useCrm.ts` hooks | T2 | Orbity `/funil` drag persists via `PATCH /api/crm/leads/{id}/stage` |

**Why not now**: pilot-products-first cadence — prove the organ on erp + Processos (2 consumers)
before fanning out. Orbity's board is stage-named differently (`leads`/`stage`, not `clientes`/`etapa_atual`),
so it's the real generality test, not a copy.

## Anti-goals (explicit non-goals)

- ❌ **Not a generic workflow engine.** `etapa_processo` is a fixed 8-stage enum mirroring the funil's
  DB-enum shape. User-configurable stages is a different product decision — don't build the abstraction
  on spec.
- ❌ **Not fixing `funil_movimentos`.** The history table exists but `mover_etapa` never writes to it.
  That's a pre-existing gap (see T3) — Processos should not *copy* the gap, but repairing Funil's
  audit trail is out of scope here.
- ❌ **No org_id on `processos_venda` unless `erp.clientes` gets one.** `clientes` is not org-scoped today
  (`migrations/027:43`). A child table scoped tighter than its parent is a false guarantee. Decide with
  the org source-of-truth roadmap, not here.
- ❌ **No drag-reorder within a column on day one** unless the organ gives it free. The funil has
  `kanban_pos`; mirror the column only if the organ's API already carries index.

## Phase 1.5 — negociação as a first-class entity (PLANNED — precedes Phase 2)

**This phase reshapes the existing Funil.** Discovered 2026-07-16 while scoping Phase 2; it is a
prerequisite for Processos de Venda, not an optional extra.

### Why it exists

The user asked for (a) `processo_venda → negociacao_id`, (b) the Funil card to carry a negociação id so
negotiation evolution can be measured per-corretor, and (c) **multiple concurrent deals per cliente**.
(c) is load-bearing: today the Funil groups `erp.clientes` by `clientes.etapa_atual`, so a cliente holds
exactly ONE stage. Two deals in flight at different stages cannot be represented. The cards must become
**negociações**, not clientes.

`erp.negociacoes` **cannot** serve this — it is the **permuta (property-swap)** table
(`ativo_origem_id` + `ativo_destino_id` + `cliente_proprietario_id` + `cliente_ofertante_id` +
`valor_permuta`). No single `cliente_id`; every row demands two properties and two parties. Reusing it
would be a category error. Hence a NEW sibling entity, permuta table untouched.

| # | Title | Files | Status | Verify recipe (live-state proof) |
|---|---|---|---|---|
| P1.5.1 | Migration: `erp.negociacoes_venda` + agency profile seed + backfill | NEW `migrations/0NN_negociacoes_venda.sql` | planned | Apply to a real DB; assert every pre-existing `clientes` row backfilled to exactly ONE `negociacoes_venda` row carrying its old `etapa_atual` — a zero-loss backfill is the whole gate |
| P1.5.2 | Corretor swappable + agency default | EDIT `backend/app/routers/clientes.py` (`ClienteCreate`/`ClienteUpdate` + line 127) | planned | Create a cliente with no corretor → lands on the agency profile; PATCH the corretor → Funil `responsavel_id` filter reflects it |
| P1.5.3 | Stage-transition log (the statistics substrate) | NEW table or reuse `erp.funil_movimentos` | planned | Move a negociação across 3 stages; assert 3 logged rows with corretor + timestamps |
| P1.5.4 | Funil reshape: cards = negociações | EDIT `backend/app/routers/funil.py`, `frontend/src/pages/Funil.tsx`, `ClienteCard.tsx`, `types/clientes.ts` | planned | Give ONE cliente two negociações at different stages; assert the board shows TWO cards in TWO columns — this is the acceptance test for the whole phase |

**Behavior guarantee**: a cliente with exactly one deal (every row today, post-backfill) renders and
behaves identically to today's board. The reshape is only visible for multi-deal clients.

**Migration ordering hazard**: `clientes.etapa_atual` stops being the source of truth. Do NOT drop the
column in the same migration that introduces `negociacoes_venda` — keep it written-but-ignored for one
release so a rollback has somewhere to land. Removal is its own later slice.

## Anti-goals (Phase 1.5)

- ❌ **Do not touch `erp.negociacoes`.** It is the permuta domain; it has its own page, router
  (`/api/negociacoes`) and `status_negociacao` enum. `negociacoes_venda` is a SIBLING, not a replacement.
  Naming them similarly is a known readability hazard — flag it if a better name surfaces.
- ❌ **Do not add a corretor column.** `erp.clientes.usuario_id` is ALREADY a `NOT NULL` FK to
  `erp.profiles`, already joined in the funil query, already filterable as `responsavel_id`. The gaps are
  swappability + the default, not existence. A second column would be a fork of an existing field.

## Open questions (to revisit at trigger time)

- **Q1**: ~~Does a `processo_venda` reference `cliente_id` alone, or also the negociação?~~ **RESOLVED
  2026-07-16** — `cliente_id` + `negociacao_venda_id` (new entity, see Phase 1.5).
- **Q2**: ~~What happens to the Funil card on acceptance?~~ **RESOLVED 2026-07-16** — it leaves the Funil
  entirely. Open sub-question: does the negociação get a terminal `aceita`/`fechado` state + `closed_at`
  (needed for cycle-time stats), or is "absent from the board" the only record? Stats need the former.
- **Q3**: Is `nota_fiscal` (stage 8) terminal, or does a processo archive after it? No `arquivado` column
  is planned — mirror `clientes.arquivado` if the board needs to stay finite.
- **Q4**: Does the organ own the dnd-kit dependency, or does each consumer keep it? Owning it in
  `@noctusai/lib` is the DRY answer but changes the lib's dep surface.
- **Q5**: `negociacoes_venda.etapa` — reuse `erp.etapa_funil`, or a new enum? Reuse couples the two
  boards' stage vocabularies; a new enum duplicates five values. Lean reuse until they diverge.
- **Q6**: Does the per-corretor statistics surface need its own page, or is it a Metas/Dashboard widget?
  The stats are the *stated motive* for Phase 1.5 but no consumer is specced — Phase 1.5 builds the
  substrate (entity + transition log), not the reporting UI. Name the consumer before building it.
- **Q7**: What is the agency profile row's identity? It needs an `auth.users` row (profiles FK to
  `auth.users(id)`) — a synthetic non-login user, or a real service account? Affects the seed migration.

## Decision log

- **2026-07-16**: Stage names fixed from the user's 8 steps → `elaboracao_contrato`, `analise_partes`,
  `revisao_contrato`, `assinatura`, `financiamento_escritura`, `finalizacao`, `entrega_chaves`,
  `nota_fiscal`. Mirrors the funil's DB-enum + TS-union + config triple.
- **2026-07-16**: Seam is the **`proposta`** column, NOT post-`fechado`. User correction to the initial
  read — accepting the proposal is what starts execution; `fechado` is a Funil-internal terminal state.
- **2026-07-16**: Organ-promotion-first chosen over build-local-and-triage-later (user decision, DRY N=3).
- **2026-07-16**: On acceptance the card **leaves the Funil entirely** (user decision) — the deal lives on
  Processos from that point.
- **2026-07-16**: `processo_venda` → `cliente_id` + `negociacao_venda_id` (user decision).
- **2026-07-16**: **Multiple concurrent deals per cliente = YES** (user decision). This is what forces
  Phase 1.5 — it makes `clientes.etapa_atual` structurally insufficient and turns Funil cards into
  negociações. Accepted knowingly: reshaping a working page is the cost of measurable negotiations.
- **2026-07-16**: `erp.negociacoes` identified as the permuta table, NOT a deal table (tech-lead finding
  against the live schema). New sibling `erp.negociacoes_venda` chosen (user decision) over repurposing.
- **2026-07-16**: Agency default = **a real seeded `erp.profiles` row** (user decision), not the org
  owner, not a synthetic null. Corretor stays `NOT NULL`; unassigned clients point at the agency.

## Retrospective (filled at first trigger fire)

*To be filled when Phase 2 fires. Capture:*
- *Was the organ's API sufficient for a second, differently-shaped board, or did Processos force a change?*
- *Did the erp Funil repoint stay behavior-identical, or did the pilot leak regressions?*
- *Lessons absorbed back to KB / MEMORY.md.*

## Composes with

- `KB § PATTERNS/architect/products-consume-canonical-organs.md` — the rule this roadmap satisfies.
- `KB § PATTERNS/frontend/product-internal-wiring.md` — route-exists ≠ wired; P2.4's verify-recipe.
- `KB § PATTERNS/architect/project-execution.md` — DRY recurrence rule (N=3 MUST formalize) + pilot-first cadence.
- `project-history/roadmaps/erp-org-source-of-truth-2026-07.md` — owns the `org_id` question (anti-goal #3).

## File trail

- This doc.
- Phase 1+ file trails land as the slices ship.
</content>
