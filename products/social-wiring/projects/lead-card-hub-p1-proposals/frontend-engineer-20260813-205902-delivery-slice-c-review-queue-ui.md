# Delivery — Slice C: review-queue UI + clientes board

**Agent:** frontend-engineer
**Project:** lead-card-hub-p1 (`products/social-wiring/projects/lead-card-hub-p1-PROJECT.md`)
**Worktree:** `.claude/worktrees/lch-p1c-review-queue-ui`, branch `feat/lch-p1c-review-queue-ui`, HEAD = origin/dev@421588ed (no divergence)

## 1. Context

Slice C of lead-card-hub Phase 1 (PROJECT.md §6). Frontend only — backend (Slices A/B)
is being built in a parallel worktree and does not exist on this branch. Everything
below is built to §5 of the PROJECT.md, never to observed behaviour. Staged, not
committed — tech-lead commits (engineer-seed protocol).

## 2. What was built

**Review queue** (`/clientes/revisao`, `pages/clientes/RevisaoFila.tsx` +
`RevisaoGrupoCard.tsx` + `hooks/useClientesRevisao.ts`) — the primary deliverable:
- Every C4/C5/C6 group with its reason code + hint copy (C5 gets stronger warning
  copy per the +5511974781330 shared-phone finding), every candidate's
  name/touch-count/contact window, and the two actions §5 names: merge, manter
  separados.
- Walkable: paginated, and a resolved group is filtered out of the LOCAL render the
  instant its mutation succeeds (never waits for/depends on refetch) so it can never
  flash back. A page that empties out purely from same-session resolutions
  auto-advances instead of stranding the operator on a blank page.
- Merge is reversible (D3) — success toast carries a "Desfazer" action wired to
  `POST /api/clientes/merges/{id}/desfazer`.
- Empty queue renders a distinct SUCCESS state (green check, "tudo certo!") — never
  the error/empty-filtered visual language.

**Board** (`/clientes`, `pages/clientes/ClientesBoard.tsx` + `hooks/useClientes.ts`) —
additive alongside the existing leads-based pages (Leads/Funil/Processos), NOT a
replacement; Phase 1 doesn't retire the `leads` table workflows:
- One card per cliente (`ClienteCard.tsx`), default active-only (D4, omits `ativo`
  param — relies on the server default rather than duplicating it client-side), an
  "Inativos" tab, and Restaurar wired to `PATCH { ativo: true }`.
- Keyless people (`identidade_incerta`) get a distinct amber "Identidade incerta"
  badge + "Sem contato identificado" instead of a phone/email — never silently read
  as a confirmed identity.
- Search, corretor filter (reused the existing `useLeadCorretores` hook rather than
  duplicating it), pagination.

**Nav**: new "Clientes" group in App.tsx, registered in BOTH `NAV_GROUPS` and
`NAV_FALLBACK` (the Imóveis trap). Both routes stay hidden until their
`status_pagina` rows exist — not seeded by this slice (backend/migration territory);
flagged below.

## 3. Organs consumed vs. built locally

`noctus.dev.find_reusable_component` returned no match for "list of person cards
with active/inactive filter" or "review queue for merging duplicate records" —
closest hits (`FilterBar`, `ChartCard`, `KanbanBoard`) are all shelfware/unrelated
shape. Per the `noc-organ-consume-check` skill's Step 4 (no-match → build local, log
the gap): `ClienteCard.tsx` and `RevisaoGrupoCard.tsx` are local, ad-hoc. Roadmap
Phase 2.1 explicitly extracts "the card face (colour strip, badge row)" into
`@noctusai/lib` — this slice's cards are the pre-extraction version; Phase 1's
checkpoint only needs "one card per human". `useLeadCorretores` (existing hook) WAS
reused for the corretor filter rather than rebuilt.

## 4. §5 assumptions called out (per brief instruction — each one flagged)

1. **Board row shape.** §4's schema columns are pinned; `touch_count`/
   `negociacoes_abertas` are NOT in §4 or §5 explicitly — assumed present on the
   board row so a card doesn't need a second request. Rendered as "—" (never a
   lying "0") if the live response omits them.
2. **PATCH body.** §5 says "PATCH .../{id} — nome, ativo/arquivado" as one phrase,
   but §4 models `ativo` and `arquivado_em` as two DISTINCT columns. Implemented
   only `{ nome?, ativo? }` — flipping `ativo: true` IS the D4 manual restore. Did
   NOT invent a separate `arquivado` write surface since §5 doesn't document its
   path.
3. **Revisao pagination — the biggest gap.** §5 explicitly lists `pagination` as a
   board-row param but NOT on the revisao row, despite the queue holding ~311 items
   and the checkpoint demanding walkability. `useRevisaoFila` requests
   `?page=&page_size=` regardless, and `normalizeRevisaoPage` (unit-tested for both
   shapes) accepts EITHER a paginated envelope (`{items,total,page,pages}`) OR a
   bare array (paginated client-side as a fallback). **If the real backend ships a
   bare array, this already works; if it ships something else entirely, this is the
   first place to check.**
4. **Merge survivor selection.** §5 names exactly two operator actions with no
   candidate-picker step. `merge()` posts no body by default (backend presumably
   picks the survivor, mirroring C3's "adopt the longest name" rule);
   `sobreviventeId` is accepted as an unused optional override in case the real
   endpoint wants one.
5. **`merge` response shape.** Only `merge_id` is depended on (to wire undo) —
   everything else passes through untyped rather than being invented.

## 5. Verify

- `npx tsc --noEmit` — clean.
- `npx vite build` — green (`✓ built in 6.15s`).
- `npx vitest run` (full product suite) — **580 passed** (baseline 550 + 30 new
  across `useClientes.test.ts`, `useClientesRevisao.test.ts`, `ClientesBoard.test.tsx`,
  `RevisaoFila.test.tsx`). Zero regressions, no flakes hit this run.
- Tests cover: groups render with reason codes; merge/manter-separados wire to the
  right mutation args; a resolved group is filtered out immediately and does not
  reappear; the undo toast's action fires `desfazer.mutate` with the real
  `merge_id`; empty queue renders the distinct success state (asserted absence of
  the error-state text); keyless people get the identidade-incerta badge and
  non-keyless people don't; the Inativos tab requests `ativo=false`; Restaurar
  PATCHes `{ ativo: true }`.

## 6. Not done / deferred

- No `ClienteDetalhes`/detail page — out of scope per PROJECT.md §6 Slice C file
  list (`pages/`, `hooks/`, `components/clientes/**`); the roadmap's Phase 2
  card-organ shell is where the rich two-pane detail lands.
- `status_pagina` rows for `clientes`/`clientes_revisao` not seeded (told explicitly
  not to flip status_pagina — tech-lead's call after browser verification).

## 7. drift-found / scoped-improvement

**drift-found:** one self-inflicted slip, corrected in-session — `noctus.dev.file_proposal`
was first called WITHOUT `worktree_path`, which wrote a delivery note into the
PRIMARY checkout at `projects/lead-card-hub-p1/proposals/` (wrong tree AND wrong
path shape — the product-scoped convention is
`products/social-wiring/projects/lead-card-hub-p1-proposals/`, confirmed by Slice
A's own note already sitting there). Caught immediately via `git status` on the
primary tree, the untracked stray directory was `rm -rf`'d (safe — untracked, never
committed), and this note was authored directly at the correct path instead.
Logged as scoped-improvement below, not drift found elsewhere.

**scoped-improvement:**
1. PROJECT.md §5's contract table lists `pagination` explicitly for the board row
   but is silent on it for the review-queue row despite the row's own prose naming a
   ~311-item collection — the same asymmetry shape that produced the 100× scaling
   bug on an earlier slice. Suggest the contract-authoring step for any list-shaped
   endpoint always states pagination explicitly, even "none — returns the full
   set", so silence stops being ambiguous between "forgot" and "deliberately
   unpaginated".
2. `noctus.dev.file_proposal(kind="delivery", project=<slug>)` has no
   `worktree_path` default-safety net the way several other MCP tools do (e.g.
   `noctus.dev.pytest`/`noctus.dev.vite_build` explicitly warn "omitting
   worktree_path silently tests/builds the PRIMARY's copy"). For a project whose
   `PROJECT.md` lives under `products/<slug>/projects/`, it also resolved to a
   top-level `projects/<slug>/proposals/` path instead of the product-scoped
   `products/<slug>/projects/<slug>-proposals/` directory the project actually
   uses (confirmed by Slice A's note living there). Suggest: (a) require/default
   `worktree_path` the same way the build/test tools do, and (b) resolve
   `project=` the same product-scoped-first way `noctus.dev.findings` already does
   ("Resolves slug across projects/ + products/*/projects/ + core/projects/").

## Return (short form)

Status: ready
Files: `products/social-wiring/frontend/src/App.tsx` (nav+routes), `src/hooks/useClientes.ts`,
`src/hooks/useClientes.test.ts`, `src/hooks/useClientesRevisao.ts`,
`src/hooks/useClientesRevisao.test.ts`, `src/pages/clientes/ClientesBoard.tsx`,
`src/pages/clientes/ClientesBoard.test.tsx`, `src/pages/clientes/RevisaoFila.tsx`,
`src/pages/clientes/RevisaoFila.test.tsx`, `src/components/clientes/ClienteCard.tsx`,
`src/components/clientes/RevisaoGrupoCard.tsx`
Tests: tsc clean · build green · vitest 580/580 (550 baseline + 30 new)
codification-events: s1=scoped-improvement logged (contract-pagination-asymmetry +
file_proposal worktree/path-resolution gap, this note) s2=none s3=none s4=none
drift-found: one self-inflicted mis-write to the primary tree, caught and corrected
in-session (see §7)
scoped-improvement: see §7 above (contract pagination asymmetry; file_proposal
worktree_path/path-resolution gap)
delivery-note: this file
Commit msg:
```
feat(social-wiring): clientes board + review-queue UI (lead-card-hub P1 Slice C)

Adds /clientes (person board, additive alongside leads pages, D4
active/inactive) and /clientes/revisao (the ~311-group C4-C6 review
queue: merge / manter-separados, reversible merge with undo toast,
empty-queue-as-success). Built to PROJECT.md §5 — backend not yet on
this branch. tsc clean, vite build green, vitest 580/580 (+30 new).
```
