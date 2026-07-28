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
`products/orbity/frontend/src/pages/Funil.tsx` appeared to be an **independent second fork** of the same
shape. On that reading a local Processos board would be the **third** instance and the DRY recurrence rule
(`N=3+ MUST formalize`) fires. User chose organ-promotion-first over ship-local-and-triage-later.

> ### ⚠️ PREMISE CORRECTED 2026-07-16 — this is N=2, not N=3
>
> Engineer D checked the claim against the tree while building the organ: **orbity's Funil does not import
> `@dnd-kit` at all.** Its card-move interaction is a click-driven dropdown menu, not drag-and-drop. So the
> real recurrence is `erp Funil + the incoming Processos board = N=2`, which under the DRY rule is
> **triage**, not MUST-formalize. The organ shipped anyway as a deliberate **accept-with-rationale**: two
> consumers are imminent and concrete, and the alternative is writing the board twice and repointing twice.
> Recorded here as an accept, NOT as a rule the evidence compelled — the original framing was wrong and
> saying so is cheaper than carrying a false premise into the next decision.
>
> **Consequence for P3.1**: repointing orbity is a drag-and-drop **UPGRADE** (a behavior change needing
> user consent), not the behavior-preserving repoint P1.3 is for erp. T2's detection signal is likewise
> wrong — it assumed a dnd-kit import that does not exist.
>
> *(Provenance: engineer-D return + commit `6b092514`. The lesson — verify the recurrence count against the
> tree BEFORE invoking the rule that the count triggers — is the reusable one.)*

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | **Organ lands + erp Funil repointed green** | `@noctusai/lib` exports `KanbanBoard`; erp Funil imports it; vitest + playwright `funil.spec.ts` green | Processos must be built on the organ, not beside it — otherwise the promotion was theater |
| T2 | ~~A 4th kanban consumer appears~~ **RETIRED — premise was false** | ~~any new `dnd-kit` import outside `@noctusai/lib`~~ | Assumed orbity was a dnd-kit consumer. It is not (see PREMISE CORRECTED above), so this trigger could never fire as written. Replaced by **T2′**. |
| T2′ | **A 3rd genuine board consumer appears** | any new `@dnd-kit` import under `products/` (i.e. outside `@noctusai/lib`) | At N=3 the DRY rule genuinely compels formalization — which the organ already satisfies, so this trigger now means "a consumer forked instead of consuming", i.e. an organ-consumption failure |
| T3 | **Funil↔Processos handoff needs an audit trail** | user asks "who accepted this proposal and when" | `erp.funil_movimentos` exists but `mover_etapa` never writes to it — a pre-existing gap this roadmap must not silently inherit |

**Status (2026-07-27)**: T1 **FIRED** — the organ landed, is registered, and the erp Funil is repointed onto
it (`da265a9f`). T2 retired as false. **T3 FIRED and is RESOLVED** — the negociação-level `mover-etapa` now
writes to `erp.funil_movimentos` (with a new `negociacao_venda_id`), so the funnel finally has an audit
trail. Phases 1.5 and 2 are SHIPPED — code on `dev`, tests green, and migrations 040 + 041 APPLIED to the
live database. **Phase 3 (orbity fan-out) SHIPPED 2026-07-28** on the user's explicit go-ahead — every
phase of this roadmap has now landed.

> ### ✅ APPLIED TO PRODUCTION 2026-07-27 — the roadmap is COMPLETE
>
> Migrations 040 + 041 were applied to `nyplttplcoyiiqjrvtiw` (the shared dev/prod project) in a SINGLE
> transaction, after the user authorised it. Post-apply verification against the live DB:
> `negociacoes=1, clientes=1, orphaned_clientes=0` (zero-loss backfill) · `orgs=25, agencies=25,
> orgless_agencies=0` · `processos=0` (correct — nothing accepted yet) · `status_pagina` row present ·
> `funil_movimentos.negociacao_venda_id` present · 10 RLS policies across the two new tables ·
> `NOTIFY pgrst, 'reload schema'` issued so PostgREST picks the new tables up.
>
> **The agency is PER-ORGANIZATION** (user decision, taken before apply — cheap then, expensive after).
> `erp.profiles.is_agency` + `erp.ensure_agency_profile(org_id)` + an AFTER INSERT trigger on
> `public.organizations` so future orgs get one automatically. `erp.agency_profile_id()` resolves the
> caller's org agency via `erp.current_org_id()`.
>
> Residual, deliberately NOT done here: `erp.clientes` / `erp.negociacoes_venda` are still not org-scoped
> (clientes has no `org_id`; its RLS is already cross-org for admins — migration 039 defers this to an
> `erp-rls-org-scope-redesign`). Giving the child tables an org_id before their parent would be a
> tighter-than-parent false guarantee.

> **Every slice carries TWO recipes, not one.** A *test-recipe* (unit/CI proof, green at the module
> boundary) is **not** a *verify-recipe* (proof against LIVE state — the page renders real rows, the
> drag persists, the button spawns a row). Tests-green ≠ verified-in-production. Fill the Verify
> recipe column for every slice; an empty one is a positive "no live check needed" claim, not a skip.

## Phase 1 — canonical KanbanBoard organ + erp Funil repoint (PARTIALLY SHIPPED)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P1.1 | Extract `KanbanBoard` / `KanbanColumn` / `KanbanCard` organ | `seed/lib/frontend/src/components/kanban/` + `components/index.ts` barrel | **shipped** `6b092514` | ⏳ **NOT yet verified against live state** — no consumer exists, so no browser drag has ever exercised it. tsc clean + 142/142 vitest is the TEST-recipe, not the verify-recipe. First real proof lands at P1.3. |
| P1.2 | Register the organ in the canonical catalog | `noctus.dev.register_organ` | **shipped** (post-merge, `source_sha=012b639a`) | ✅ `register_organ("KanbanBoard")` → `registered, rows_written=1` from the primary tree at dev `06d6f945`. NOTE: this leg CANNOT complete in-dispatch — `register_organ` has no `worktree_path` param and resolves `REPO_ROOT` to the MCP server's startup workspace, so it never sees worktree-only files (s1 logged against `mcp/noctusai/settings.py`). Tech-lead must re-run post-merge every time. |
| P1.3 | Repoint erp Funil onto the organ (pilot #1) | EDIT `products/erp-imobiliario/frontend/src/pages/Funil.tsx`, `components/clientes/ColunaFunil.tsx`, `ClienteCard.tsx` | **shipped** `da265a9f` | ✅ Playwright drives a REAL browser drag across columns and asserts the move POST fires (`e2e/tests/funil.spec.ts`) — this is the first real exercise of the organ's INTERACTION, closing P1.1's honesty note. 18/18 e2e green. |

**✅ P1.3 blocking follow-up — RESOLVED (2026-07-27), and resolved one level up.** The `@dnd-kit` triple was
missing from `FRAMEWORK_DEPS`. Rather than hand-add three entries to a list that had *already* proven it
drifts, the factory now DERIVES organ peer deps by scanning `seed/lib/frontend/src` at config time —
mirroring the derivation the Python audit tool grew on 2026-07-20 (`_derive_organ_transitive_deps`) as its
build-time twin. Verified identical to the Python side's 16 entries. The derivation also surfaced
`@radix-ui/react-tabs` + `recharts` as previously un-deduped organ deps nobody had noticed.

The failure mode this prevents is silent, not loud: without `resolve.dedupe` the organ's dnd-kit and the
product's resolve to two module instances, so a card's `useDraggable` reads a different `DndContext` than
the board rendered and the drag simply no-ops.

**Honesty note on P1.1's test coverage**: real pointer/keyboard `@dnd-kit` event simulation was NOT
attempted — jsdom doesn't compute the `getBoundingClientRect` layout math the sensors need. The drag
resolution logic was extracted as a pure `computeMove` helper and unit-tested directly against both card
shapes instead. That's an honest proof of the LOGIC and an explicit non-proof of the INTERACTION. The
interaction is unverified until a browser drives it at P1.3.

**Behavior guarantee**: the ERP Funil's runtime behavior does not change — same columns, same drag,
same optimistic update. This is a pure structural repoint. Any visible change is a regression.

**Why ship now**: building Processos on a local fork and promoting later means writing the board
twice and repointing twice. The organ is cheapest before the third consumer exists, not after.

## Phase 2 — Processos de Venda (DEFERRED — fires when T1 ∧ Phase 1.5 landed)

| # | Title | Files | Trigger | Verify recipe (write it now, run it when it ships) |
|---|---|---|---|---|
| P2.1 | Migration: `etapa_processo` enum + `processos_venda` table (FK → `clientes` **+ `negociacoes_venda`**) + `status_pagina` row + index | `migrations/041_processos_venda.sql` | **shipped + APPLIED** | Apply to a real DB; `\d erp.processos_venda`; confirm the `status_pagina` row exists (without it the nav item silently never renders) |
| P2.2 | Backend router + DTO service | `routers/processos_venda.py`, `services/processos_venda_service.py`, mounted in `main.py` | **shipped** | `curl /api/processos-venda` on a live ERP container → real grouped columns, not `[]` |
| P2.3 | Accept-proposal seam | `POST /api/negociacoes-venda/{id}/aceitar-proposta` | **shipped** | Accept a proposal on a real negociação in `proposta`; assert exactly one `processos_venda` row spawns at `elaboracao_contrato`, the negociação leaves the Funil board, and a double-click yields ONE row (idempotency) |
| P2.4 | Frontend page on the organ + nav + route | `pages/ProcessosVenda.tsx`, `components/processos/ProcessoCard.tsx`, `types/processos.ts`, `lib/etapasProcessoConfig.ts`, `hooks/useProcessos.ts`, `App.tsx` | **shipped** | Page shows real rows; drag persists; sidebar entry renders under Funil de Vendas |
| P2.5 | "Aceitar Proposta" button on the Funil card, `proposta` column only | `components/clientes/NegociacaoCard.tsx` | **shipped** | Click the button on a `proposta` card in a browser → card leaves Funil, appears on Processos. Handler MUST `e.stopPropagation()` — the card body carries dnd-kit drag listeners |
| P2.6 | Tests | `test_processos_venda_router.py`, `test_negociacoes_venda_router.py`, `e2e/tests/processos-venda.spec.ts`, EDIT `funil.spec.ts` + `sidebar.spec.ts` | **shipped** | — (this row IS the test-recipe; its verify-recipe is P2.1–P2.5's) |

**Trigger**: T1 (organ green on the Funil pilot) **and** Phase 1.5 landed — `processos_venda.negociacao_venda_id`
has nothing to reference until the entity exists.

**Why not now**: a Processos board written before the organ is the third fork the DRY rule forbids; and
built before Phase 1.5 it would hang off `cliente_id` alone and need re-migrating once negociações exist.

## Phase 3 — orbity Funil fan-out (SHIPPED 2026-07-28, on user's go-ahead)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P3.1 | Repoint orbity Funil onto the organ (pilot #2) | EDIT `products/orbity/frontend/src/pages/Funil.tsx`; NEW `src/pages/__tests__/Funil.test.tsx` | **shipped** | Orbity `/funil` drag persists via `PATCH /api/crm/leads/{id}/stage` — see the browser leg below |
| P3.2 | Product vitest harness can render an organ at all | EDIT `seed/framework/frontend/vitest.config.factory.ts` + export `resolveFrameworkDeps` from `vite.config.factory.ts` | **shipped** | 11 product suites re-run: dev-team 11/11, personal-finance 30/30, social-wiring 409/409 — identical to their pre-change baselines |

**The generality test passed.** Orbity's vocabulary really is different — `leads`/`stage_id` with free-form,
org-owned stage ROWS (name + colour + position), against the ERP's `clientes`/`etapa` DB enum. The organ
needed **no change**: `getCardStage` absorbed the nullable `stage_id`, `renderColumnHeader` absorbed the
colour dot the organ's id+label `KanbanStage` deliberately doesn't carry, and the `data-kanban-column-id`
child selector absorbed a completely different column skin. The one seam that felt thin — the organ hard-codes
its column BODY className — was already solved by the ERP pilot via a Tailwind arbitrary-child variant, so
pilot #2 reused it instead of growing a `columnBodyClassName` prop. Zero organ edits across two consumers
with disjoint vocabularies is the actual evidence that the extraction was right.

**Drag is an UPGRADE here, not a repoint.** Pre-organ, orbity's only way to move a card was a per-card
"mover para etapa" dropdown; there was no dnd-kit tree at all (this is the PREMISE CORRECTION that retired
T2). The dropdown is KEPT — it is a precise, pointer-cheap affordance on a wide board, and deleting a
working control is not part of adopting an organ.

**Fixed on contact, one level up (P3.2).** The first attempt to render the organ in a product vitest died on
`Cannot read properties of null (reading 'useState')` — the classic dual-React. `vite.config.factory.ts`
has carried `resolve.dedupe` since forever, so the BUILD was always fine; `vitest.config.factory.ts`
claimed in its own docstring to "mirror" it but had no dedupe at all. No product had ever rendered an organ
under vitest, so the hole was invisible. Fixed by EXPORTING `resolveFrameworkDeps` from the vite factory and
reusing it — one derivation, two factories, rather than a second hand-maintained list
(`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`).

Two self-inflicted regressions were caught by re-running the whole fleet rather than just orbity, and both
are now encoded in the factory's comments:
- **Deduping a dep the product doesn't own is a hard error, not a no-op.** `dedupe` means "resolve from the
  project root"; personal-finance has no `@dnd-kit/*`, so the unfiltered list turned a working fallback into
  `Failed to resolve import`. The list is now filtered by what the product actually installed.
- **`resolve.alias` must stay an OBJECT.** Switching it to Vite's array form broke `products/dev-team`,
  whose `extend` hook does `{...peerAlias, ...config.resolve.alias}` — spreading an array into an object
  yields `{0:…,1:…}` and silently drops every alias, including `@`. Key ORDER carries the subpath-before-bare
  requirement instead.

**Also fixed on contact:** orbity's loading gate was `if (isLoading)`, with `stages.length === 0` →
"Nenhuma etapa configurada" right behind it — the lying-loading shape
(`KB § PATTERNS/frontend/lying-loading-state.md`). After `seed-defaults` invalidates the funil, `isLoading`
is false mid-refetch, so the page would offer "Criar etapas padrão" for a funnel whose stages are already on
the wire. Now `isPending || (isFetching && stages.length === 0)`: `isFetching` is scoped to the EMPTY case
on purpose, so resolved data stays on screen through a background refetch instead of flashing back to a
skeleton. Regression-tested three ways (first load / mid-refetch / settled-and-genuinely-empty).

**⏳ The browser leg is the one thing NOT proven here.** jsdom has no layout, so dnd-kit's collision
detection has nothing to measure — a page test can prove the organ is mounted and its drag wiring attached
(`data-kanban-card-id` / `data-kanban-column-id` are emitted only by the organ), and that card clicks still
reach the detail panel, but it cannot prove a drag lands. The ERP pilot closed this with Playwright;
**orbity has no e2e harness**. See the decision log for why that was not installed in this slice.

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
| P1.5.1 | Migration: `erp.negociacoes_venda` + agency profile seed + backfill | `migrations/040_negociacoes_venda.sql` | **shipped + APPLIED** | Apply to a real DB; assert every pre-existing `clientes` row backfilled to exactly ONE `negociacoes_venda` row carrying its old `etapa_atual` — a zero-loss backfill is the whole gate |
| P1.5.2 | Corretor swappable + agency default | EDIT `backend/app/routers/clientes.py` | **shipped (with a deliberate deviation — see below)** | Create a cliente with no corretor → lands on the agency profile; PATCH the corretor → Funil `responsavel_id` filter reflects it |
| P1.5.3 | Stage-transition log (the statistics substrate) | REUSE `erp.funil_movimentos` + `negociacao_venda_id`; written by the negociação `mover-etapa` | **shipped** | Move a negociação across 3 stages; assert 3 logged rows with corretor + timestamps |
| P1.5.4 | Funil reshape: cards = negociações | EDIT `routers/funil.py`, `pages/Funil.tsx`, `pages/ClienteDetalhes.tsx`, `hooks/useFunil.ts`; `ClienteCard.tsx` → `NegociacaoCard.tsx` | **shipped** | Give ONE cliente two negociações at different stages; assert the board shows TWO cards in TWO columns — this is the acceptance test for the whole phase |

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
- **Q3**: ~~Is `nota_fiscal` terminal, or does a processo archive after it?~~ **RESOLVED 2026-07-27** —
  terminal, plus an `arquivado` flag mirroring `clientes.arquivado`. Without it the last column grows
  without bound and the board stops being readable within a year.
- **Q4**: ~~Does the organ own the dnd-kit dependency, or does each consumer keep it?~~ **RESOLVED
  2026-07-27** — both, correctly: the organ declares it, every product already lists it, and the vite
  factory now DERIVES the dedupe set from the organ source so the two can't drift.
- **Q5**: ~~`negociacoes_venda.etapa` — reuse `erp.etapa_funil`, or a new enum?~~ **RESOLVED 2026-07-27** —
  reuse, as the roadmap leaned. A parallel enum would duplicate five values on day one.
- **Q6**: Does the per-corretor statistics surface need its own page, or is it a Metas/Dashboard widget?
  **STILL OPEN — deliberately.** Phase 1.5 built the SUBSTRATE (negociação entity + `closed_at` +
  `funil_movimentos` transitions carrying corretor + timestamps). No reporting UI was built: no consumer is
  specced, and the anti-goal says name the consumer first. The data now exists to build it whenever you want.
- **Q7**: ~~What is the agency profile row's identity?~~ **RESOLVED 2026-07-27** — a synthetic non-login
  `auth.users` row at a deterministic UUID (`…0a6e0c`), with the profile created by the existing
  `handle_new_user` trigger rather than duplicated. Resolver: `erp.agency_profile_id()`.
  **NEW sub-question for the user**: ONE global agency vs one per org, in a 25-org product — see
  "Awaiting user decision" at the top.
- **Q8 (NEW, 2026-07-27)**: `erp.clientes.etapa_atual` is now written-but-ignored. Its removal is a
  deliberate later slice (the rollback landing zone). **Trigger**: after one release with 040 applied and
  the board stable.
- **Q9 (NEW, 2026-07-27)**: 89 pre-existing TypeScript errors across 53 files in erp-imobiliario are
  currently unguarded — `tsc --noEmit` checks ZERO files because `tsconfig.json` is solution-style
  (`"files": []` + references). See the decision log entry. **Trigger**: before any "the types are clean"
  claim is made about this product.

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
- **2026-07-27**: `FRAMEWORK_DEPS` fixed by DERIVATION, not by adding three entries — the list had already
  drifted once, so patching the instance would have left the class alive.
- **2026-07-27**: **Deliberate deviation from the P1.5.2 recipe.** The roadmap said "create a cliente with no
  corretor → lands on the agency". Implemented as: explicit assignment wins (including explicitly TO the
  agency, which is how you unassign); otherwise the CREATOR owns it. Reason, found only by reading the live
  policies: `clientes`/`negociacoes_venda` SELECT RLS is `has_role(admin) OR auth.uid() = <owner>`, so an
  agency-owned row is INVISIBLE to the corretor who just created it — they would fill in the form and watch
  the record vanish. The agency remains the DB-level DEFAULT (satisfying NOT NULL for service-role/import
  paths with no real corretor) and the explicit unassign target.
- **2026-07-27**: `clientes` INSERT RLS widened by exactly one alternative to admit the agency sentinel —
  the decided default was otherwise structurally un-insertable.
- **2026-07-27**: Q2 resolved with a CHECK tying `closed_at` to `status`, so a closed deal cannot exist
  without its timestamp (which would read as cycle-time zero in the very statistics the phase exists for).
- **2026-07-27**: Accept-proposal idempotency placed in a UNIQUE CONSTRAINT
  (`processos_venda.negociacao_venda_id`), not a router check — a check-then-insert races under concurrent
  double-clicks. The second call returns the existing processo with 200, not an error.
- **2026-07-27**: `ClienteDetalhes`' stage control now acts on the cliente's single OPEN negociação, and goes
  read-only (pointing at the Funil) when there are zero or several. Leaving it writing `clientes.etapa_atual`
  would have been a silent no-op — the user changes the stage and the board never moves.
- **2026-07-27**: **Did NOT mirror 040/041 into `001_erp_imobiliario.sql`.** The single-001 convention says
  live-DB patches are `002+` AND mirrored back. Migrations 030-039 were never mirrored, so mirroring only
  mine would leave 001 half-current — which reads as more trustworthy than it is. Surfaced as pre-existing
  drift rather than silently half-fixed.
- **2026-07-27**: **`tsc --noEmit` on this product checks ZERO files** (solution-style `tsconfig.json`:
  `"files": []` + `references`). The real invocation is `tsc -p tsconfig.app.json --noEmit`, which reports 90
  pre-existing errors across 54 files. This slice's own broken import (a deleted export still imported by
  `ClienteDetalhes`) passed the "type check" and was caught only by the vite build. Fixed the one error in a
  file this slice touched (90 → 89); the remaining 89 are pre-existing and logged as Q9. **The gate itself is
  unfixed** — changing the npm script / CI invocation would surface 89 failures fleet-wide and is the user's
  scoping call, not an agent's.
- **2026-07-28**: Orbity's **"mover para etapa" dropdown is KEPT** alongside drag. Drag is additive here
  (orbity had no dnd-kit at all); removing a working control is not part of adopting an organ, and the
  dropdown remains the cheaper affordance on a wide board.
- **2026-07-28**: The organ was **not extended** for pilot #2. The one candidate — a `columnBodyClassName`
  prop, since the organ hard-codes its column body's className — was rejected because the ERP pilot already
  solved it through the `data-kanban-column-id` attribute + a Tailwind arbitrary-child variant. Adding a
  prop for a need an existing seam already covers is how an organ's API bloats.
- **2026-07-28**: `resolveFrameworkDeps` **exported** from `vite.config.factory.ts` and consumed by
  `vitest.config.factory.ts` rather than restated. The vitest factory's docstring had claimed to "mirror"
  the vite one while missing its `resolve.dedupe` entirely — the mirror was aspirational, and a second
  hand-maintained list would have re-created the exact drift the derivation was built to kill.
- **2026-07-28**: `dedupe` is **filtered to deps the product actually installed**. Deduping means "resolve
  from the project root", so naming a package the product lacks converts a working fallback into a hard
  resolution failure (personal-finance, no `@dnd-kit/*`, whole suite red). Discovered only by re-running all
  11 consumer suites — orbity alone was green throughout.
- **2026-07-28**: `resolve.alias` **stays an object map** in the vitest factory. Vite's array form is the
  more correct shape for ordered matching, but it is a BREAKING change to the factory's contract:
  `products/dev-team`'s `extend` hook spreads `config.resolve.alias` as a record, and spreading an array
  into an object silently produces `{0:…,1:…}` — dropping every alias including `@`. Ordered object keys
  carry the subpath-before-bare requirement instead.
- **2026-07-28**: **No Playwright harness installed for orbity.** The drag-lands proof is browser-only and
  orbity has no e2e setup; installing one means a new dev dependency, browser binaries, a config, and a
  mock layer — a harness slice in its own right, not a rider on a page repoint. The page tests instead
  assert the organ's own drag-wiring attributes plus a click-not-swallowed case, and the gap is stated
  rather than papered over. Named destination: a `orbity-e2e-harness` slice, or the fleet-wide e2e-per-organ
  leg that `KB § PATTERNS/common/agent-context-architecture.md`'s sibling organ-knowledge work already
  contemplates.

## Retrospective (2026-07-27 — Phases 1.3 / 1.5 / 2 built)

**Was the organ's API sufficient for a second, differently-shaped board?** Yes — unchanged. Processos has a
different card type, a different stage-id union (8 values vs 5), a different value field (`valor` vs
`valor_estimado`) and a different empty-state, and all of it went through `getCardId` / `getCardStage` /
`renderCard` / `renderColumnHeader` without touching `@noctusai/lib`. The genericity was real, not asserted.
The organ's `isLoading`/`error`/`loadingState` props were used by Processos and not by Funil — worth noting
the two consumers diverged on which states they delegate.

**Did the repoint stay behavior-identical?** The organ repoint (P1.3) did. The Phase 1.5 RESHAPE deliberately
did not — that was the point — but the single-deal case renders identically, which is the guarantee that was
promised.

**Lessons worth carrying (candidates for KB / MEMORY absorption):**
1. **A hand-maintained list that has drifted once will drift again — derive it instead.** `FRAMEWORK_DEPS`
   had already been patched reactively on the Python side; the TS side was still hand-maintained and still
   wrong. Fixing the instance would have left the class alive.
2. **Verify the gate before trusting the green.** `tsc --noEmit` on a solution-style `tsconfig.json`
   type-checks ZERO files and exits 0 — a permanently-green gate. It hid 90 real errors and would have hidden
   this slice's own broken import; the vite build caught what the "type check" did not. Every prior
   "tsc clean" claim about this product, including in this roadmap's P1.1 row, was vacuous.
3. **Read the RLS before designing a default.** The decided agency-default was in direct conflict with
   `clientes`' live INSERT policy, and defaulting a deal to the agency would have made it invisible to its
   own creator. Neither is visible from the schema alone — only from the policies.
4. **Idempotency belongs in a constraint, not a check-then-insert.** `UNIQUE(negociacao_venda_id)` makes the
   double-click impossible rather than unlikely; the router's pre-check is an ergonomics layer on top.
5. **`BEGIN … <migration> … probe … ROLLBACK` is a real verify-recipe for a migration** against a shared
   dev/prod DB — it proves the apply against the LIVE schema while persisting nothing.

## Composes with

- `KB § PATTERNS/architect/products-consume-canonical-organs.md` — the rule this roadmap satisfies.
- `KB § PATTERNS/frontend/product-internal-wiring.md` — route-exists ≠ wired; P2.4's verify-recipe.
- `KB § PATTERNS/architect/project-execution.md` — DRY recurrence rule (N=3 MUST formalize) + pilot-first cadence.
- `project-history/roadmaps/erp-org-source-of-truth-2026-07.md` — owns the `org_id` question (anti-goal #3).

## File trail

- This doc.
- Phase 1+ file trails land as the slices ship.
</content>
