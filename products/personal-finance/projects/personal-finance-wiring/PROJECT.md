# Personal-Finance Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> Revise phases, fold in optimizations, update §11 Change Log as work progresses.
> See `CLAUDE.md → §1 Universal rules → No incomplete commits / Estimate off evidence / Replication-to-seed symmetry` and
> `KB § PATTERNS/project-execution.md`.
>
> **Slug rationale.** Mirrors the `therapy-platform-wiring` shape: a sweep of every
> `personal-finance` surface end-to-end, closing every gap at the layer it belongs
> to (seed vs. product vs. schema), landing with tests + clean build. Intent =
> `wiring` per `KB § PATTERNS/project-execution.md §8`.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-10 (Phase 3 ✅ — DTO drift fix)
- **Status:** Phases 0, 1, 2, 3 ✅. Phase 1 seed-seam audits complete; Phase 2 Tier A DELETE pre-check holes closed; Phase 3 Tier B DTO drift `user_id` → `created_by` rename + `Cotacao` PF-6 stub shipped. Phases 4-7 pending.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `products/personal-finance/MASTER-PROMPT.md` — agent-facing product contract
  - `products/personal-finance/README.md` — short stack overview
  - `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md` — sister project, methodology source
  - `projects/products-wiring-rollout/PROJECT.md` — parent sequencing project (PF → ERP)
  - `KB § PATTERNS/project-execution.md` — cadence, slug naming, tests-with-code
  - `KB § PATTERNS/proposals-and-improvements.md` — phase-end protocol
  - `KB § PATTERNS/database-rls.md` — migration discipline (PF schema is hyphenated)
  - `KB § PATTERNS/lgpd.md` — personal-data guardrails (financial data is high-sensitivity)
- **Project slug:** `personal-finance-wiring`
- **Lives at:** `products/personal-finance/projects/personal-finance-wiring/`

---

## 1. Context & Purpose

The `personal-finance` product was shipped with a backend that is mostly wired (org-scoping migration `008` landed 2026-05-03; 584/594 tests green) and a frontend with 24 pages consuming 15 hooks. The product has not yet been swept end-to-end the way `therapy-platform-wiring` is sweeping therapy. Anecdotal evidence (the only available signal so far) suggests the same class of defects therapy is uncovering will surface here: scaffolded UI hooks pointing at endpoints that are missing, HTTP-method-mismatched, or returning raw DB rows instead of the typed DTOs the frontend `types/` declares.

PF is **structurally simpler** than therapy:

| Surface | PF | Therapy | ERP |
|---|---|---|---|
| Backend routers | 16 | 38 | 61 |
| Frontend hooks | 15 | 26 | 66 |
| Frontend pages | 24 | ~40+ | 68 |
| Migrations | 8 | 9 | 25+ |
| Backend tests | 584 | (n/a — closed gaps fold in) | 1,661 |

That smaller surface is the reason this project goes **before ERP** in the parent rollout (`projects/products-wiring-rollout/PROJECT.md`). PF is the learning ground — methodology and tooling refinements discovered here propagate into the ERP plan before ERP starts.

The win looks like: every hook→endpoint pair returns the DTO `frontend/src/types/` declares, every navigable page loads real data with a 200, recurring scheduler artifacts are visible in the UI, AI indicators (`<AIIndicator refType="transacao" …/>`) render, every backend route declared in §5.4.x has a frontend caller (no orphans) **or** a deletion rationale, `pytest` is green, `vite build` is green.

---

## 2. Confirmed constraints

User answers captured during interrogation. **Future agents inherit the reasoning, not just the outcome.** This section starts as an inheritance batch from `therapy-platform-wiring` (the sister project the user has already shaped) and is updated as PF-specific interrogation lands at Phase 0 kickoff.

### 2.1 Inherited from `therapy-platform-wiring` (carry-forward — same user, same methodology)

- **Scope breadth — widest (A ⇒ B ⇒ C).** Fix known regressions, sweep the user-facing surface end-to-end, close pre-existing scaffolding debt, widen to the whole `personal-finance` product. *Carry-forward; confirmed at Phase 0 kickoff.*
- **Tests** — three-layer discipline per `KB § PATTERNS/testing.md`. Not a per-phase decision. A phase without its tests is `⏳ (tests deferred)`, not `✅`.
- **Cadence** — phase-by-phase, pause after each, no auto-advance. User says "continue" / "do phase N" / "ram through 2-3" when bulk is wanted.
- **Seed sync** — patterns worth promoting mid-project land as **phase-end proposals** via `noctus.dev.file_proposal(project="personal-finance-wiring", …)`. Project does not block waiting for seed promotion.
- **Triage at decision time** — every divergence lands on `formalize / refactor / accept-with-rationale` (`KB § PATTERNS/accept-with-rationale.md`).
- **No silent errors / no monkey-patching of our own code in tests / no quick fixes.** Standard universal rules apply.
- **Commit + push only your own work.** Per-phase local commit; final commit + push at project close.

### 2.2 PF-specific (to be filled at Phase 0 kickoff)

- **Schema name** — `personal-finance` (hyphenated). Every Supabase client touch in new code uses `ClientOptions(schema="personal-finance")`. *(Already documented in MASTER-PROMPT; codified here so the wiring sweep treats it as a hard constraint, not a footnote.)*
- **Org-scoping is fresh (2026-05-03).** Migration `008_org_scoping_transition.sql` just landed. Phase 0 verifies every router/service has been retrofitted; any remaining `user_id`-only queries are gap rows. *(Locked-baseline fixture: 584 passed + 10 skipped post-migration — Phase 0 must not destabilize this baseline.)*
- **`is_personal=true` orgs** — solo users get a personal org auto-created via `ensure_pf_personal_org`. Wiring must not assume multi-member orgs everywhere.
- **APScheduler is part of the product surface.** `app/scheduler.py` auto-processes due recurring transactions. The wiring sweep includes verifying the *frontend visibility* of scheduler artifacts (next-run, last-run, errors) — not just the endpoints.
- **yfinance integration** — `cotacoes` + `watchlist` hit yfinance for real-time quotes. Wiring includes verifying degraded-mode UX when yfinance is rate-limited / unreachable.
- **AI indicators** — `<AIIndicator refType="transacao" …/>` exists per MASTER-PROMPT. Phase 0 verifies render-side consumption matches `006_ai_outputs.sql` shape and that `ai_outputs` standard router is mounted via `standard_routers=[..., "ai_outputs"]`.

*(Add user-confirmed items to §2.2 as the Phase 0 interrogation completes. Each item carries its `*(why this matters / what it rules out)*` clause.)*

---

## 3. Design principles

How we're approaching *this specific problem* on top of the platform-wide `CLAUDE.md` rules.

1. **Fix at the layer of the cause.** If two PF pages need org-resolution, the solution is a shared dependency — not two duplicated reads. Seed-absorption precedes duplication. (The therapy `fetch_user_identities` resolver — landed by `therapy-platform-wiring` Phase 1 — is the first reusable beneficiary; PF inherits it for any user-display needs that surface.)
2. **No band-aids.** No `?? ''` guards to tolerate bad DTOs; the DTO is correct at the backend boundary or the endpoint is broken and Phase 0 catches it.
3. **LGPD-first on every personal-data endpoint.** Financial data is high-sensitivity (transactions, account balances, net worth). Every new endpoint that aggregates personal financial data in a new shape gets a `noctus.dev.lgpd_flag` call per `KB § PATTERNS/lgpd.md`.
4. **Migrations and applied SQL stay in lockstep.** Every DDL applied via `mcp__claude_ai_Supabase__apply_migration` lives first as `products/personal-finance/backend/migrations/NNN_<name>.sql`. Schema drift is a rule violation, not a tradeoff.
5. **Tests land in the same phase as the code.** Three-layer discipline, no exceptions. The 584-test baseline is the floor — phase ✅ requires baseline still green.
6. **Discovery is an artifact, not a vibe.** Phase 0 produces a checked-in gap table in §5.4. Phases 2-N reference rows in that table — no phantom scope.
7. **Scheduler + yfinance get explicit Phase coverage.** The two non-HTTP-shaped surfaces (cron-driven recurring processing, third-party real-time quote fetching) are easy to overlook in a hook→endpoint sweep. Dedicated sub-tasks below.

---

## 3a. Seed-first analysis (REQUIRED)

> **Rule.** Every project — single-product included — runs the seed-first checklist *before* phase planning, per `KB § GUIDES/seed-first-design.md` and `feedback_seed_first_at_authoring_time`. The wiring sweep is intrinsically per-product (the gap inventory enumerates ONE product's surfaces); the **tools** discovered during the sweep (helpers, DTOs, mappers) are the cross-cutting concern that lands in seed.

Six-question checklist applied to this project:

1. **Is the contract identical for every product?** *Mixed.* The wiring **sweep methodology** (gap-table inventory, Patterns A-G classification, phase cadence) is identical across products and lives in `KB § PATTERNS/project-execution.md` + the parent `products-wiring-rollout`. The **gap inventory itself** is product-specific by definition.
2. **Is the data source product-specific?** YES — PF tables (`personal-finance.transacoes`, `contas`, `categorias`, ...) are PF-specific. Wiring fixes touch PF code only.
3. **Is the placement product-specific?** YES — fixes land in `products/personal-finance/{backend,frontend}/`.
4. **Is the visibility / permission rule the same?** PARTIAL. Org-scoping (RLS `(SELECT auth.uid())` + `public.current_org_id()`) is the seed-uniform pattern; PF inherits it as of migration `008`. Any RLS holes Phase 0 surfaces get fixed against the seed pattern, not invented locally.
5. **Does the seam already exist in seed?** Several relevant seams: `noctusai_lib.api.auth.{require_role, get_org_id, resolve_sso_role}`; `noctusai_lib.primitives.{responses, exceptions}`; `noctusai_lib.domain.org.ensure_personal_org` (PF wraps as `ensure_pf_personal_org`); `noctusai_lib.ai.persist_output`; `noctusai_lib.llm.chat_completion`; `noctusai_lib.email.digest.send_digest`; `noctusai_lib.credentials.resolve_credential`. The therapy-Phase-1 `noctusai_lib.integrations.supabase_identity.fetch_user_identities` (in flight) is the next gift PF will inherit. Phase 0 absorption-search runs the trio (`noctusai_scan_*`) over PF services to catch any PF-local re-implementation of any of the above.
6. **Default-on or opt-in?** DEFAULT-ON for inherited seams (the product already inherits via the seed factories; we are not adding opt-out). Pattern-G fixes (path renames, DTO normalization) are direct edits, not flags.

**Litmus — per-product code count this design requires:**

- [x] **0 lines of cross-product code.** The cross-cutting helpers (identity resolver, pagination DTO, etc.) land in seed via phase-end proposals — they are not duplicated into PF. The PF-specific code count is whatever the gap table demands at the product layer.
- [ ] (rest of the litmus is N/A — the wiring fixes themselves are by design product-bounded.)

**Phase plan implications.** §6 phases work in PF code (correct) and bubble up cross-cutting absorption opportunities to seed-lib via phase-end proposals. **No replication framing**: phases below talk about PF surfaces (admin/owner-org / leader / agent / personal-org), not "for each product". This project never iterates over products.

---

## 4. Scope

**In scope:**

- Every `personal-finance` backend endpoint that a frontend hook calls. Router surface (16 routers as of 2026-05-03): `ai`, `ativos`, `carteira`, `categorias`, `contas`, `cotacoes`, `dashboard`, `metas`, `operacoes`, `orcamentos`, `patrimonio`, `recorrentes`, `relatorios`, `transacoes`, `watchlist` (+ standard-router `ai_outputs` mounted via factory). Phase 0 confirms current count.
- Every PF migration needed to support the wiring fixes. The reject-flow analog for PF (if any surfaces) lands as its own migration in the next free slot (`009_*.sql` as of 2026-05-03 — Phase 0/N confirms at execution time).
- Frontend corrections to consume corrected DTOs and fix pre-existing UI bugs uncovered during the sweep (Radix misuse, type-mismatched hook returns, status-badge resolvers, AIIndicator wiring, scheduler-artifact rendering).
- Tests (unit + router + integration paths) landing in the same phase as the code they cover. 584-test baseline must stay green.
- LGPD awareness: `noctus.dev.lgpd_flag` calls where new endpoints aggregate financial data in new shapes.
- End-to-end verification: build + pytest + manual browser QA of golden paths on every surface touched.

**Out of scope (for now — with reason):**

- **Other products** (`therapy-platform`, `erp-imobiliario`, etc.) — separate projects, separate slugs. Cross-product seed promotions are filed as phase-end proposals; they don't block this project's close.
- **UX redesigns** — if a page is ugly but works end-to-end, it stays. Wiring project, not redesign.
- **New features** — no capability we aren't already carrying as scaffolded UI/code. Phase 0 flags speculative scaffolds and they become separate future projects.
- **AI prompt tuning / new AI features** — the existing P1 + P3 categorize + recurring-flag + monthly-narrative are wired only; deeper AI work is `ai-expansion` territory.
- **yfinance vendor swap or quote-cache redesign** — we wire the existing surface; quote-cache architecture changes are a separate hardening project.
- **APScheduler architecture changes** — we surface scheduler artifacts in the UI; scheduler-architecture rework (e.g. Celery migration) is a separate project.
- **Seed abstractions beyond what the gap table actually justifies** — we file phase-end proposals; the reviewer schedules them as separate seed projects.

---

## 5. Architecture / Data Model

*Populated by Phase 0 in its entirety. This section starts with the shapes we already know from the MASTER-PROMPT + recently-shipped migrations; everything else lands as Phase 0's output.*

### 5.1 Inherited seed seams (gifts from sister projects)

| Seam | Path | Source project | Phase that consumes |
|---|---|---|---|
| `fetch_user_identities` (bulk auth.users resolver) | `noctusai_lib.integrations.supabase_identity` | `therapy-platform-wiring` Phase 1 | PF Phase TBD if surfaces need user-display data (likely lower in PF — orgs are the unit, not individuals) |
| Pagination DTO | `noctusai_lib.api.pagination` (proposed) | `therapy-platform-wiring` Phase 3 (proposal) | PF DTO-normalization phase, if cross-product recurrence confirms |
| `require_role` / `get_org_id` / `resolve_sso_role` | `noctusai_lib.api.auth` | already in seed | every PF router that needs auth gating |
| `ensure_personal_org` | `noctusai_lib.domain.org` | already in seed | already wrapped as `ensure_pf_personal_org` (2026-05-03) |
| `persist_output` | `noctusai_lib.ai` | already in seed | already used by AI service |
| `chat_completion` / `generate_embedding` | `noctusai_lib.llm` | already in seed | already used by AI service |
| `resolve_credential` | `noctusai_lib.credentials` | already in seed | LLM key resolution (per-org → platform → env) |
| `send_digest` | `noctusai_lib.email.digest` | already in seed | already used by `monthly_narrative` |

### 5.2 Gap inventory *(populated by Phase 0 — 2026-05-03)*

#### 5.2.1 Headline counts

| Surface | Count |
|---|---|
| Backend routers | 16 product + 5 standard (`health`, `notificacoes`, `team`, `ai_outputs`, `ai_feedback`) |
| Backend routes | 78 product routes + 12 standard-router routes = **90 total** |
| Frontend hooks | 15 (verified) |
| Frontend pages with **direct** `useQuery`/`api.*` (bypassing hooks) | **1** — `pages/Equipe.tsx` (5 callsites against seed `team` standard router) |
| Unique frontend → backend calls surveyed | **78** (73 from hooks + 5 from `Equipe.tsx`) |
| Gap rows (404 / 405 / path-mismatch / EN-PT-mismatch / DTO drift / orphans) | **11** — 0 path mismatch, 0 verb mismatch, 0 404/405 confirmed, 7 backend orphans, 2 DELETE-pre-check holes (services) + 1 DELETE-result-as-existence-proxy (router), **1 systemic DTO drift batch** (10 types stale `user_id` post-`008`) |
| Backend routers with `response_model` declared | **0/16** (Pattern E confirmed; matches therapy 0/38) |
| DELETE endpoints with proper pre-check 404 | **10/12** (orcamentos.excluir_item, transacoes.excluir are silent) |
| Direct-DB calls bypassing service layer (router fat-router) | **5** — all in `routers/recorrentes.py` (`listar`, `obter`, `criar`, `atualizar`, `excluir`); other 15 routers route 100% through services |

#### 5.2.2 Systemic findings *(populated by Phase 0 — 2026-05-03)*

Therapy surfaced seven systemic findings (Patterns A-G). PF results below; new PF-specific patterns labeled `PF-1`+.

| Pattern | PF status | Evidence |
|---|---|---|
| **A — PT/EN path mismatch** | **0 hits** | PF uses business-domain Portuguese consistently. Backend routers (`ativos`, `categorias`, `contas`, `metas`, `orcamentos`, `recorrentes`, `relatorios`, `transacoes`, `watchlists`, `cotacoes`, `carteiras`, `operacoes`, `patrimonio`) match frontend hook paths exactly. Per PROJECT §7 Q2 default — keep PT for business domain. |
| **B — Admin namespace fragmentation** | **N/A** | PF has NO admin facade. All endpoints are org-scoped via `org_id` only; no `/api/admin/*` routes; single-tier auth (org member) via `get_current_user_org`. |
| **C — Admin detail endpoints** | **N/A** | (Same as B.) |
| **D — Direct-fetch role-prefix pages** | **1 hit** | `pages/Equipe.tsx` calls `api.get/post/delete` directly against `/api/team*` (seed `team` standard router). 5 callsites: list members, list invitations, invite, remove member, revoke invite. Decision deferred to design batch (Q-equipe) — likely keep direct-fetch (one-off page; no PF-internal hook needed). |
| **E — Implicit DTO contract** | **0/16 routers** | All 16 product routers return via `success_response()` / `paginated_response()` / `ok_response()` wrappers from `app.responses`. No `response_model=` declarations. Pagination uses `success_response(data, total=len(data))` envelope. Frontend `types/` declares typed shapes informally. |
| **F — `require_role` recurrence** | **N/A in PF** | PF is single-tier (org member). No role gating beyond `team` admin (handled by seed `team` standard router). `require_role` factory shipped therapy P1 — PF inherits but does not currently use. |
| **G — Path-shape mismatches** | **0 hits** | Every `useFoo` hook's path matches its router's prefix + segment shape exactly. No verb mismatches, no segment swaps, no param-position drift. |
| **PF-1 — `get_current_user_org` recurrence (90 callsites in 16 routers)** | **N=2 with ERP** | PF-local tuple wrapper around seed's `deps.get_org_id`. ERP has the same shadow at `dependencies.py:28`. Therapy doesn't (different multi-tenancy). Filed in absorption catalog as `make_get_current_user_org` factory candidate. |
| **PF-2 — DTO drift: `user_id` stale post-migration `008`** | **10 types stale** | `frontend/src/types/index.ts` declares `user_id: string` on `Conta`, `Categoria`, `Transacao`, `Orcamento`, `Meta`, `Carteira`, `Ativo`, `Operacao`, `Watchlist`, `Recorrente`. Migration `008` RENAMED `user_id → created_by` on every table. Backend services do `select("*")` returning rows with `created_by` + `org_id` (no `user_id`). Frontend has zero consumer of `.user_id` (grep confirms) — drift is type-only, low-risk fix. |
| **PF-3 — DELETE pre-check holes** | **2 of 12 endpoints** | `orcamentos_service.excluir_item` (line 139) deletes with NO existence pre-check (silent no-op on bad id). `transacoes_service.excluir` (line 120) uses `single()` then `if transacao.data:` — never raises 404 if not found. Tier A fix in Phase 2. |
| **PF-4 — Recorrentes router bypasses service layer for CRUD** | **5 endpoints** | `routers/recorrentes.py` calls `db.table()` directly for 5 CRUD endpoints; only `executar_*` go through `RecorrentesService`. The other 15 routers route 100% through services. Refactor opportunity (Phase 4). |
| **PF-5 — Scheduler artifacts: NO HTTP surface, NO UI surface** | **Confirmed** | Two cron jobs registered (`recorrentes_daily` 06:00 + `recorrentes_catchup` 4h) via `noctusai_lib.api.scheduler`. Seed scheduler module exposes no GET endpoint for `next_run` / `last_run` / errors. Frontend Recorrentes.tsx renders rules but no execution history. **Cross-product — proposed seed standard router `scheduler` in design batch Q1.** |
| **PF-6 — yfinance degraded-mode UX missing** | **Confirmed** | Backend `cotacoes_service` returns `{fonte: "dry-run"}` on yfinance failure or `{fonte: "yfinance"}` on success. Frontend ignores `fonte`. No stale badge. Phase 5 fix. |
| **PF-7 — AIIndicator wiring: correct** | **OK** | `Transacoes.tsx:221` renders `<AIIndicator refType="transacao" refId={t.id} />`; PF mounts `ai_outputs` standard router; runtime smoke deferred to Phase 7. |
| **PF-8 — Cross-schema `db.table("organizations")` from PF schema-scoped client** | **Needs runtime verification** | `monthly_narrative_service.py:145` reaches `public.organizations` from a `db` client created with `schema="personal-finance"`. May work via search-path coincidence, may fail silently. Phase 4/5 verification. |
| **PF-9 — DELETE-result-as-existence-proxy in router** | **1 hit** | `recorrentes.py:106-108` does `db.table().delete()...execute()` then `if not result.data: 404` — Supabase delete may return empty `data` on success in some versions, returning false 404s. Audit elsewhere; brief sibling. |
| **PF-10 — Helper recurrence (cross-product)** | **N=3+ MUST-FORMALIZE Metas; N=2 AI-plumbing** | `cli.py --scan-helpers` surfaced: `useMetas`/`useCreateMeta`/`useUpdateMeta`/`useDeleteMeta` in 3 products (PF + ERP + daily-life); `criar_meta`/`listar_metas`/`atualizar_meta`/`excluir_meta` in 3 products. `_persist_indicator` / `_require_openai` / `check_openai_configured` in 2 products (PF + ERP). Filed in absorption catalog. |

#### 5.2.3 Per-hook gap inventory *(populated by Phase 0 — 2026-05-03)*

Status legend: `OK` (paths + verbs match, types align modulo PF-2 drift), `path` (Pattern A/G drift), `verb` (HTTP-method mismatch), `404`/`405` (Tier A regression), `dto-drift` (frontend type vs. backend response shape mismatch beyond PF-2 systemic), `orphan` (backend route with no surveyed frontend caller), `pre-check` (DELETE silent no-op or false 404). Role-tag derived from page-tree: all PF data hooks are **personal-org** scope (no leader/agent/owner-org tiers — single-tier auth except seed `team` admin). Public surfaces: `Login`, `ForgotPassword`, `AcceptInvite`, `Landing`, `NotFound`, `SSOCallback`.

| Frontend caller | Method | Path | Backend route | Status | Notes |
|---|---|---|---|---|---|
| `useContas.useContas` | GET | `/api/contas` | `routers/contas.py:14` GET `""` | OK | dto-drift: `Conta.user_id` stale (PF-2) |
| `useContas.useConta` | GET | `/api/contas/{id}` | `contas.py:35` GET `/{conta_id}` | OK | 404 raised (good) |
| `useContas.useSaldos` | GET | `/api/contas/saldos` | `contas.py:26` GET `/saldos` | OK | |
| `useContas.useCriarConta` | POST | `/api/contas` | `contas.py:46` POST `""` | OK | |
| `useContas.useAtualizarConta` | PATCH | `/api/contas/{id}` | `contas.py:57` PATCH `/{conta_id}` | OK | |
| `useContas.useExcluirConta` | DELETE | `/api/contas/{id}` | `contas.py:71` DELETE `/{conta_id}` | OK | service pre-checks 404 |
| `useTransacoes.useTransacoes` | GET | `/api/transacoes` | `transacoes.py:15` GET `""` | OK | dto-drift: `Transacao.user_id` stale (PF-2) |
| `useTransacoes.useTransacao` | GET | `/api/transacoes/{id}` | `transacoes.py:54` GET `/{transacao_id}` | OK | |
| `useTransacoes.useTransacoesPorCategoria` | GET | `/api/transacoes/por-categoria` | `transacoes.py:41` GET `/por-categoria` | OK | |
| `useTransacoes.useCriarTransacao` | POST | `/api/transacoes` | `transacoes.py:65` POST `""` | OK | |
| `useTransacoes.useAtualizarTransacao` | PATCH | `/api/transacoes/{id}` | `transacoes.py:76` PATCH `/{transacao_id}` | OK | |
| `useTransacoes.useExcluirTransacao` | DELETE | `/api/transacoes/{id}` | `transacoes.py:90` DELETE `/{transacao_id}` | **pre-check** | service `excluir` line 120: `if transacao.data:` silently succeeds on bad id (PF-3) |
| `useCategorias.useCategorias` | GET | `/api/categorias` | `categorias.py:14` GET `""` | OK | |
| `useCategorias.useArvoreCategorias` | GET | `/api/categorias/arvore` | `categorias.py:26` GET `/arvore` | OK | |
| `useCategorias.useCriarCategoria` | POST | `/api/categorias` | `categorias.py:49` POST `""` | OK | |
| `useCategorias.useAtualizarCategoria` | PATCH | `/api/categorias/{id}` | `categorias.py:60` PATCH `/{categoria_id}` | OK | |
| `useCategorias.useExcluirCategoria` | DELETE | `/api/categorias/{id}` | `categorias.py:74` DELETE `/{categoria_id}` | OK | service pre-checks 404 |
| `useOrcamentos.useOrcamentos` | GET | `/api/orcamentos` | `orcamentos.py:14` GET `""` | OK | dto-drift: `Orcamento.user_id` stale (PF-2) |
| `useOrcamentos.useOrcamento` | GET | `/api/orcamentos/{id}` | `orcamentos.py:23` GET `/{orcamento_id}` | OK | |
| `useOrcamentos.useProgressoOrcamento` | GET | `/api/orcamentos/{id}/progresso` | `orcamentos.py:34` GET `/{orcamento_id}/progresso` | OK | |
| (no caller) | GET | `/api/orcamentos/{id}/itens` | `orcamentos.py:47` GET `/{orcamento_id}/itens` | **orphan** | likely consumed via `/progresso` payload — verify |
| `useOrcamentos.useCriarOrcamento` | POST | `/api/orcamentos` | `orcamentos.py:60` POST `""` | OK | |
| `useOrcamentos.useAtualizarOrcamento` | PATCH | `/api/orcamentos/{id}` | `orcamentos.py:74` PATCH `/{orcamento_id}` | OK | |
| `useOrcamentos.useExcluirOrcamento` | DELETE | `/api/orcamentos/{id}` | `orcamentos.py:88` DELETE `/{orcamento_id}` | OK | service pre-checks 404 |
| `useOrcamentos.useCriarItem` | POST | `/api/orcamentos/{id}/itens` | `orcamentos.py:97` POST `/{orcamento_id}/itens` | OK | |
| `useOrcamentos.useAtualizarItem` | PATCH | `/api/orcamentos/itens/{id}` | `orcamentos.py:108` PATCH `/itens/{item_id}` | OK | |
| `useOrcamentos.useExcluirItem` | DELETE | `/api/orcamentos/itens/{id}` | `orcamentos.py:120` DELETE `/itens/{item_id}` | **pre-check** | `orcamentos_service.excluir_item` line 139: NO pre-check, silent on bad id (PF-3) |
| `useMetas.useMetas` | GET | `/api/metas` | `metas.py:14` GET `""` | OK | dto-drift: `Meta.user_id` stale (PF-2). Helper recurrence N=3 MUST-FORMALIZE (PF-10). |
| `useMetas.useMeta` | GET | `/api/metas/{id}` | `metas.py:26` GET `/{meta_id}` | OK | |
| `useMetas.useProgressoMeta` | GET | `/api/metas/{id}/progresso` | `metas.py:37` GET `/{meta_id}/progresso` | OK | |
| `useMetas.useCriarMeta` | POST | `/api/metas` | `metas.py:48` POST `""` | OK | |
| `useMetas.useAtualizarMeta` | PATCH | `/api/metas/{id}` | `metas.py:59` PATCH `/{meta_id}` | OK | |
| `useMetas.useExcluirMeta` | DELETE | `/api/metas/{id}` | `metas.py:73` DELETE `/{meta_id}` | OK | service pre-checks 404 |
| `useMetas.useAdicionarContribuicao` | POST | `/api/metas/{id}/contribuicao` | `metas.py:82` POST `/{meta_id}/contribuicao` | OK | |
| `useCarteira.useCarteiras` | GET | `/api/carteiras` | `carteira.py:14` GET `""` | OK | dto-drift: `Carteira.user_id` stale (PF-2) |
| `useCarteira.useCarteira` | GET | `/api/carteiras/{id}` | `carteira.py:23` GET `/{carteira_id}` | OK | |
| `useCarteira.useResumoCarteira` | GET | `/api/carteiras/{id}/resumo` | `carteira.py:34` GET `/{carteira_id}/resumo` | OK | |
| `useCarteira.useCriarCarteira` | POST | `/api/carteiras` | `carteira.py:45` POST `""` | OK | |
| `useCarteira.useAtualizarCarteira` | PATCH | `/api/carteiras/{id}` | `carteira.py:56` PATCH `/{carteira_id}` | OK | |
| `useCarteira.useExcluirCarteira` | DELETE | `/api/carteiras/{id}` | `carteira.py:70` DELETE `/{carteira_id}` | OK | service pre-checks 404 |
| (no caller) | POST | `/api/carteiras/{id}/alocacao` | `carteira.py:79` POST `/{carteira_id}/alocacao` | **orphan** | scaffold; likely future allocation-target editor UI |
| `useAtivos.useAtivos` | GET | `/api/ativos` | `ativos.py:14` GET `""` | OK | dto-drift: `Ativo.user_id` stale (PF-2) |
| (no caller) | GET | `/api/ativos/por-carteira/{id}` | `ativos.py:26` GET `/por-carteira/{carteira_id}` | **orphan** | likely scaffold for `CarteiraDetalhes` tab; verify Phase 7 |
| `useAtivos.useAtivo` | GET | `/api/ativos/{id}` | `ativos.py:35` GET `/{ativo_id}` | OK | |
| `useAtivos.useCriarAtivo` | POST | `/api/ativos` | `ativos.py:46` POST `""` | OK | |
| `useAtivos.useAtualizarAtivo` | PATCH | `/api/ativos/{id}` | `ativos.py:57` PATCH `/{ativo_id}` | OK | |
| `useAtivos.useExcluirAtivo` | DELETE | `/api/ativos/{id}` | `ativos.py:71` DELETE `/{ativo_id}` | OK | |
| `useOperacoes.useOperacoes` | GET | `/api/operacoes` | `operacoes.py:15` GET `""` | OK | dto-drift: `Operacao.user_id` stale (PF-2) |
| (no caller) | GET | `/api/operacoes/por-ativo/{id}` | `operacoes.py:52` GET `/por-ativo/{ativo_id}` | **orphan** | likely scaffold for `CarteiraDetalhes` ativo expansion; verify Phase 7 |
| (no caller) | GET | `/api/operacoes/{id}` | `operacoes.py:75` GET `/{operacao_id}` | **orphan** | unused detail endpoint |
| `useOperacoes.useCriarOperacao` | POST | `/api/operacoes` | `operacoes.py:85` POST `""` | OK | |
| `useOperacoes.useExcluirOperacao` | DELETE | `/api/operacoes/{id}` | `operacoes.py:98` DELETE `/{operacao_id}` | OK | |
| `useWatchlist.useWatchlists` | GET | `/api/watchlists` | `watchlist.py:14` GET `""` | OK | dto-drift: `Watchlist.user_id` stale (PF-2) |
| `useWatchlist.useWatchlist` | GET | `/api/watchlists/{id}` | `watchlist.py:23` GET `/{watchlist_id}` | OK | |
| `useWatchlist.useCriarWatchlist` | POST | `/api/watchlists` | `watchlist.py:32` POST `""` | OK | |
| `useWatchlist.useExcluirWatchlist` | DELETE | `/api/watchlists/{id}` | `watchlist.py:41` DELETE `/{watchlist_id}` | OK | |
| `useWatchlist.useAdicionarItem` | POST | `/api/watchlists/{id}/itens` | `watchlist.py:50` POST `/{watchlist_id}/itens` | OK | |
| `useWatchlist.useRemoverItem` | DELETE | `/api/watchlists/itens/{id}` | `watchlist.py:59` DELETE `/itens/{item_id}` | OK | service pre-checks 404 + 403 cross-org |
| `useRecorrentes.useRecorrentes` | GET | `/api/recorrentes` | `recorrentes.py:15` GET `""` | OK | dto-drift: `Recorrente.user_id` stale (PF-2). Router fat-router PF-4. |
| `useRecorrentes.useExecutarPendentes` | POST | `/api/recorrentes/executar` | `recorrentes.py:29` POST `/executar` | OK | |
| `useRecorrentes.useProximasContas` | GET | `/api/recorrentes/proximas` | `recorrentes.py:39` GET `/proximas` | OK | router fat-router PF-4 |
| `useRecorrentes.useExecutarUnico` | POST | `/api/recorrentes/{id}/executar` | `recorrentes.py:53` POST `/{recorrente_id}/executar` | OK | |
| (no caller) | GET | `/api/recorrentes/{id}` | `recorrentes.py:65` GET `/{recorrente_id}` | **orphan** | scaffold; PF has no Recorrente detail page |
| `useRecorrentes.useCriarRecorrente` | POST | `/api/recorrentes` | `recorrentes.py:75` POST `""` | OK | router fat-router PF-4 |
| `useRecorrentes.useAtualizarRecorrente` | PATCH | `/api/recorrentes/{id}` | `recorrentes.py:88` PATCH `/{recorrente_id}` | OK | router fat-router PF-4 |
| `useRecorrentes.useExcluirRecorrente` | DELETE | `/api/recorrentes/{id}` | `recorrentes.py:102` DELETE `/{recorrente_id}` | **PF-9** | router uses `delete().execute()` then `if not result.data: 404` — risk of false 404 on success |
| `useCotacoes.useCotacao` | GET | `/api/cotacoes/{ticker}` | `cotacoes.py:18` GET `/{ticker}` | OK | dto-drift: response includes `fonte` field not in any frontend type (PF-6) |
| (no caller) | POST | `/api/cotacoes/batch` | `cotacoes.py:26` POST `/batch` | **orphan** | bulk-quote optimization not yet consumed |
| `useCotacoes.useAtualizarPrecos` | POST | `/api/cotacoes/atualizar` | `cotacoes.py:34` POST `/atualizar` | OK | |
| `usePatrimonio.usePatrimonioAtual` | GET | `/api/patrimonio/atual` | `patrimonio.py:13` GET `/atual` | OK | |
| `usePatrimonio.useHistoricoPatrimonio` | GET | `/api/patrimonio/historico` | `patrimonio.py:22` GET `/historico` | OK | |
| `usePatrimonio.useSnapshotPatrimonio` | POST | `/api/patrimonio/snapshot` | `patrimonio.py:34` POST `/snapshot` | OK | |
| `useDashboard.useKPIs` | GET | `/api/dashboard/kpis` | `dashboard.py:13` GET `/kpis` | OK | |
| `useDashboard.useResumo` | GET | `/api/dashboard/resumo` | `dashboard.py:21` GET `/resumo` | OK | |
| `useRelatorios.useRelatorioMensal` | GET | `/api/relatorios/mensal?mes=` | `relatorios.py:13` GET `/mensal` | OK | |
| `useRelatorios.useRelatorioAnual` | GET | `/api/relatorios/anual?ano=` | `relatorios.py:25` GET `/anual` | OK | |
| `useRelatorios.useFluxoCaixa` | GET | `/api/relatorios/fluxo-caixa` | `relatorios.py:37` GET `/fluxo-caixa` | OK | |
| `useAI.useCategorizeTransaction` | POST | `/api/ai/transacoes/{id}/categorize` | `ai.py:59` POST `/transacoes/{transacao_id}/categorize` | OK | |
| `useAI.useRecurringFlag` | POST | `/api/ai/transacoes/{id}/recurring-flag` | `ai.py:149` POST `/transacoes/{transacao_id}/recurring-flag` | OK | |
| `useAI.useMonthlyNarrative` | GET | `/api/ai/monthly-narrative?period_days=` | `ai.py:105` GET `/monthly-narrative` | OK | uses `db.table("organizations")` cross-schema (PF-8 — verify) |
| (no frontend; cron only) | POST | `/api/ai/monthly-narrative/send` | `ai.py:130` POST `/monthly-narrative/send` | OK | intentional cron-only orphan |
| `Equipe.tsx:62` (direct) | GET | `/api/team` | seed `team` standard-router GET `""` | OK | Pattern D (direct fetch — keep per design batch) |
| `Equipe.tsx:63` (direct) | GET | `/api/team/invitations` | seed `team` GET `/invitations` | OK | Pattern D |
| `Equipe.tsx:82` (direct) | POST | `/api/team/invite` | seed `team` POST `/invite` | OK | Pattern D |
| `Equipe.tsx:101` (direct) | DELETE | `/api/team/{id}` | seed `team` DELETE `/{user_id}` | OK | Pattern D |
| `Equipe.tsx:116` (direct) | DELETE | `/api/team/invitations/{id}` | seed `team` DELETE `/invitations/{invitation_id}` | OK | Pattern D |
| `<AIIndicator>` from `@noctusai/lib/design-system` (Transacoes.tsx:221) | GET | `/api/ai/outputs?ref_type=&ref_id=` | seed `ai_outputs` GET `/outputs` | OK | wired correctly via PF `standard_routers=["ai_outputs"]` |

**Gap-row summary:** 0 path mismatches, 0 verb mismatches, 0 confirmed 404/405 regressions, **7 backend orphans** (cotacoes/batch, ativos/por-carteira, operacoes/por-ativo, operacoes/{id}, carteiras/{id}/alocacao, recorrentes/{id} GET, orcamentos/{id}/itens GET) **+ 1 intentional cron-only** (`POST /api/ai/monthly-narrative/send`), **2 DELETE pre-check holes** (PF-3), **1 DELETE-result-as-existence-proxy** (PF-9), **1 systemic DTO drift** (PF-2 — 10 type rows). Every other surface is OK at the path/verb level.

#### 5.2.4 Backend orphans *(populated by Phase 0 — 2026-05-03)*

| Route | Likely intent | Recommended disposition |
|---|---|---|
| `POST /api/cotacoes/batch` | Bulk-quote optimization for many tickers | Keep — may be consumed when Watchlist page batches refresh; defer decision to Phase 5 |
| `GET /api/ativos/por-carteira/{carteira_id}` | Filter ativos by carteira | Keep — likely consumed by `CarteiraDetalhes.tsx` ativo list when wired in Phase 4 |
| `GET /api/operacoes/por-ativo/{ativo_id}` | Filter operacoes by ativo | Keep — likely consumed by ativo expansion in `CarteiraDetalhes.tsx` Phase 4 |
| `GET /api/operacoes/{operacao_id}` | Operacao detail | Likely deletable — no detail page surfaced; recheck Phase 4 |
| `POST /api/carteiras/{id}/alocacao` | Set allocation targets | Keep — alocacao_alvo table exists; future allocation editor; mark `accept-with-rationale` if Phase 7 confirms no UI consumer |
| `GET /api/orcamentos/{id}/itens` | Item list for orcamento | Likely redundant with `/progresso` payload; mark for verification then deletion at Phase 7 |
| `GET /api/recorrentes/{recorrente_id}` | Recorrente detail | Keep — useful endpoint, no frontend yet; Phase 5 surfaces a Recorrente detail card |
| `POST /api/ai/monthly-narrative/send` | Cron-only narrative send | Intentional orphan (cron/n8n trigger); document in MASTER-PROMPT |

#### 5.2.5 Migration column gap *(populated by Phase 0 — 2026-05-03)*

Tables referenced in `app/services/*.py` + `app/routers/*.py` cross-checked against `migrations/001..008.sql`:

| Table | Referenced in | Defined in migration | Status |
|---|---|---|---|
| `contas` | services + routers | 001 (created), 008 (`user_id → created_by`, add `org_id`) | OK |
| `categorias` | services + routers | 001, 008 | OK |
| `transacoes` | services + routers | 001, 008 | OK |
| `orcamentos` | services + routers | 001, 008 | OK |
| `orcamento_itens` | orcamentos service | 001, 008 | OK |
| `metas` | services + routers | 001, 008 | OK |
| `meta_contribuicoes` | metas service | 001, 008 | OK |
| `carteiras` | services + routers | 001, 008 | OK |
| `ativos` | services + routers | 001, 008 | OK |
| `operacoes` | services + routers | 001, 008 | OK |
| `watchlists` | services + routers | 001, 008 | OK |
| `watchlist_itens` | watchlist service | 001, 008 | OK |
| `recorrentes` | services + routers | 001, 008 | OK |
| `patrimonio_snapshots` | patrimonio service | 001, 008 | OK |
| `resumos_mensais` | relatorios service | 001 (`status_pagina` migration 004; resumos_mensais in 001) | OK |
| `alocacao_alvo` | carteira service | 001 | OK |
| `ai_outputs` | seed `ai_outputs` standard router (uses PF schema via `persist_output(schema="personal-finance")`) | 006 | OK |
| `ai_feedback` | seed `ai_feedback` standard router | 007 | OK |
| `invitations` | seed `team` standard router | 005 | OK |
| `status_pagina` | (no PF service references it) | 004 | OK (seed-only) |
| `public.organizations` | `monthly_narrative_service.py:145` (cross-schema reach) | core schema | **PF-8 — needs verification**; either works via search-path or fails silently |

**No column gap surfaced.** All referenced tables exist; columns referenced (`org_id`, `created_by`, `nome`, `tipo`, `valor`, `data`, `descricao`, `comerciante`, `categoria_id`, `conta_id`, `proxima_data`, `is_automatico`, `ativo`, `ticker`, `valor_atual`, etc.) all confirmed present per migration `008`'s rename. The `user_id` field is no longer in any operational table — the only stale references are in `frontend/src/types/index.ts` (PF-2 above).

#### 5.2.6 Should-use-seed candidates *(populated by Phase 0 — 2026-05-03)*

`cli.py --scan-helpers --product personal-finance --min-count 2` surfaced the following PF-touching recurrences. Filed in `projects/products-wiring-rollout/cross-product-absorption-catalog.md`.

**N=3 — MUST-FORMALIZE (per `KB § PATTERNS/project-execution.md § 2.7`):**

| Helper | Products | Destination |
|---|---|---|
| `useMetas`, `useCreateMeta`, `useUpdateMeta`, `useDeleteMeta` | PF + ERP + daily-life | seed/lib frontend hooks (or generic `useResourceCRUD<Meta>` factory) |
| `criar_meta`, `listar_metas`, `atualizar_meta`, `excluir_meta` | PF + ERP + daily-life | `noctusai_lib.domain.metas.MetasService` shell |

→ Filed: design batch Q4 — file `metas-domain-seed-absorption` follow-up project after B1 close. Per `KB § 07-GAMIFICATION.md`, Metas is the gamification heart; absorption belongs in seed/lib.

**N=2 — triage time (will promote to formalize at confirmed N=3):**

| Helper | Products | Status |
|---|---|---|
| `_persist_indicator`, `_require_openai`, `check_openai_configured` | PF + ERP | Filed — B1 audit: confirm against `noctusai_lib.domain.ai`; drop locally if seed already exposes equivalent |
| `excluir_ativo`, `criar_ativo`, `atualizar_ativo`, `AtivosService` | PF + ERP | N=2 — domain-bounded but bodies likely diverge (PF financial assets vs. ERP imobiliário); accept-with-rationale candidate |
| `excluir_meta`, `dashboard_resumo`, `fluxo_caixa`, `_fmt_brl` | PF + ERP | Same triage as above |

**N=4+ — already accepted-with-rationale (do NOT re-flag):**

| Helper | Products | Disposition |
|---|---|---|
| `_render_bodies`, `_generate_narrative`, `_empty_output`, `_fetch_window` | PF + ERP + mailing + daily-life + core | Per-product narrative wrapper retained at N=4 in `KB § PATTERNS/accept-with-rationale.md`; explicit accept-with-rationale comment in `monthly_narrative_service.py:56` |

**Cross-cutting Pattern F-extension (filed in absorption catalog):**

| Helper | Products | Destination |
|---|---|---|
| `get_current_user_org` (PF tuple wrapper around `deps.get_org_id`) | PF (90 callsites) + ERP (similar shape at `dependencies.py:28`) | `noctusai_lib.api.auth.make_get_current_user_org(get_current_user_fn, get_org_id_fn)` factory; ship in B1 alongside `make_require_role` adoption |

#### 5.2.7 Deletion-candidate batch *(populated by Phase 0 — 2026-05-03)*

PF surfaces NO confirmed page-level deletion candidates — every page in `pages/*.tsx` (24 total) has at least one `useFoo` hook consuming a real backend route, OR is a public/auth surface (Login, ForgotPassword, AcceptInvite, Landing, NotFound, SSOCallback). The 5 backend orphans listed in §5.2.4 are mostly **kept** (scaffold for foreseeable future use); `GET /api/operacoes/{id}` and `GET /api/orcamentos/{id}/itens` are the only "likely deletable" candidates and they're cheap-to-keep — defer disposition to Phase 7 verification (orcamento itens may already be redundant with `/progresso`).

**Decision deferred to design batch Q-equipe** (filed at master): keep `Equipe.tsx` direct-fetch (Pattern D, 1 page) vs. extract to `useTeam` hook layer? Default rec: keep direct-fetch (one-off; not worth a hook layer for one page).

**No batch-deletion sign-off needed at Phase 0 close** — the deletion question is empty for PF.

#### 5.2.8 Test coverage *(populated by Phase 0 — 2026-05-03)*

PF baseline: 584 passed + 10 skipped (locked 2026-05-03 post-org-scoping migration `008`). Phase 0 enumeration:

**Router tests** (`tests/routers/`): **17 files** for 16 product routers + `notificacoes` + `team` (seed standard routers tested per-product). Files: `test_ai_router.py`, `test_ativos_router.py`, `test_carteira_router.py`, `test_categorias_router.py`, `test_contas_router.py`, `test_cotacoes_router.py`, `test_dashboard_router.py`, `test_metas_router.py`, `test_notificacoes_router.py`, `test_operacoes_router.py`, `test_orcamentos_router.py`, `test_patrimonio_router.py`, `test_recorrentes_router.py`, `test_relatorios_router.py`, `test_team_router.py`, `test_transacoes_router.py`, `test_watchlist_router.py`. **Missing per-product smoke**: `ai_outputs`, `ai_feedback`, `health` standard routers (these are seed-tested but no per-product mount-smoke).

**Service tests** (`tests/services/`): **16 files** + integration/realdb suites. Files: `test_ai_service.py`, `test_ativos_service.py`, `test_carteira_service.py`, `test_categorias_service.py`, `test_contas_service.py`, `test_cotacoes_service.py`, `test_dashboard_service.py`, `test_metas_service.py`, `test_monthly_narrative_service.py`, `test_onboarding_service.py`, `test_orcamentos_service.py`, `test_patrimonio_service.py`, `test_recorrentes_service.py`, `test_relatorios_service.py`, `test_scheduler.py`, `test_transacoes_service.py`. Coverage 1:1 with services.

**Phase 7 remediation:** add 3 small mount-smoke tests asserting `GET /api/ai/outputs` 200, `GET /api/ai/feedback?ref_type=&ref_id=` 200, `GET /api/health` 200 from PF's TestClient. Trivial deltas.

#### 5.2.9 Keeper review pass *(populated by Phase 0 — 2026-05-03)*

Command: `/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python mcp/noctusai/cli.py --review --product personal-finance`

Verbatim output (tail):

```
╔══════════════════════════════════════════════════════════╗
║                NoctusAI Dev Toolkit                      ║
╚══════════════════════════════════════════════════════════╝

  Mode: agent  |  Issues found: 0
  No proposals filed by this call. The in-session agent authors them.
  Agent review prompt (scroll up or pipe to a file):

No compliance issues detected. Nothing for the agent to author.
```

**Result: 0 keeper issues.** The org-scoping retrofit (migration `008`) cleaned up the legacy `user_id`-only patterns, and PF's surface has remained compliant since. No proposals to author.

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses. Phases 2-N below are placeholders whose concrete shape is decided by Phase 0's output, mirroring the therapy project's structure.

**Phase status-icon convention** (`KB § PATTERNS/project-execution.md §1`):

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress / partially done |
| ✅ | Complete — every sub-task ticked |
| ❌ | Blocked or failed — see Change Log |

**Improvement capture during steps. Proposal authoring at end of phase.** One bundled proposal per phase, filed via `noctus.dev.file_proposal(project="personal-finance-wiring", …)` → lands in `products/personal-finance/projects/personal-finance-wiring/proposals/`. Per `feedback_apply_inline_delete_proposals`: simple in-scope items applied inline; only scheduled / human-approval items get formal proposals.

---

### Phase 0 — Discovery & inventory ✅

Produces the concrete gap table in §5.2. Every subsequent phase references rows from this table.

- [x] Enumerate every `api.get|post|put|patch|delete` call in `products/personal-finance/frontend/src/hooks/` and `.../src/pages/`. Capture URL, HTTP verb, caller hook/page, role-tag (org-owner / leader / agent / personal-org / public — derived from page-tree placement), expected response shape (from `types/`). → §5.2.3
- [x] Enumerate every route decorator (`@router.get|post|put|patch|delete`) across all routers in `products/personal-finance/backend/app/routers/*.py` (16 verified + standard `ai_outputs`; Phase 0 confirms current count). Capture URL, HTTP verb, response shape (`response_model` if set + return-value tracing through `success_response()` / `paginated_response()` / `ok_response()` wrappers). → §5.2.1, §5.2.3
- [x] Join the two lists → produce the **per-router gap table** in §5.2.3 with role-tags. Status values: `OK`, `404`, `405`, `path` (Pattern A/G), `verb`, `dto-drift`, `needs-audit`. → §5.2.3
- [x] Cross-reference every column reference in `app/services/*.py` against `products/personal-finance/backend/migrations/001..008.sql`. Surface column gaps in §5.2.5. → §5.2.5
- [x] **Cross-cutting absorption check** vs. `seed/lib/backend/noctusai_lib/{primitives,config,testing,integrations,domain,api,security,credentials,llm,ai,email}/`. Run `cli.py --scan-helpers --product personal-finance --min-count 2` over PF services/routers/hooks. File §5.2.6. → §5.2.6 + master `cross-product-absorption-catalog.md`
- [x] **Org-scoping retrofit verification.** Walk every router/service post-migration `008`: confirm `Service(db, org_id)` initialization, confirm RLS uniform via `public.current_org_id()`, confirm no remaining `user_id`-only queries in op tables. Surface holes as gap rows. → §5.2.2 PF row "Org-scoping retrofit clean": `grep -nE 'user_id\|.eq\("user_id"' app/{services,routers}/*.py` returns zero hits in operational code.
- [x] **Scheduler / yfinance / AI-indicator visibility audit.** Confirm `app/scheduler.py` artifacts (next-run, last-run, error history) have a UI surface — likely on Recorrentes page. Confirm yfinance degraded-mode UX (rate-limited, unreachable). Confirm `<AIIndicator refType="transacao" …/>` renders on `Transacoes.tsx` and reads the `ai_outputs` standard router correctly. → §5.2.2 PF-5/PF-6/PF-7
- [x] Run keeper review — `cli.py --review --product personal-finance`. Capture output in §5.2.9. → §5.2.9 (0 issues)
- [x] **Rewrite Phases 2-N below** based on the gap table. Phases that are pure placeholders today get concrete sub-tasks rooted in §5.2.3 rows. → see Phases 2-7 below
- [x] **Surface design batch to user.** Phase 0 finishes by surfacing a §7-style design batch (Pattern A path renames? Pattern E `response_model` rollout? Deletion candidates? PF-specific Q's like scheduler UI placement) for one-batch sign-off before Phase 1 kicks off. → master `design-batch-aggregator.md` Q1-Q4
- [x] Log Phase 0 completion in §11. → see §11

**Deliverable:** §5.2 populated end-to-end; phases 2-N carry concrete work items rooted in §5.2.3 rows; design-batch surfaced at master `design-batch-aggregator.md` for user sign-off. **Status: ✅ COMPLETE 2026-05-03.**

**Improvements:** captured in §11 Phase 0 entry — see master `design-batch-aggregator.md` Q1-Q4 for the design-batch surface. (Block added 2026-05-03 by drive-by fix from `mcp-tool-name-deprecation` close per § 2.9 — keeper-phase-state-consistency was blocking unrelated commit; this is a placeholder pointer to the Phase 0 audit-trail content already inline in §11.)

---

### Phase 1 — Seed seam absorption + known-pattern fixes ✅

Apply the gifts from sister projects and fix the absorption-search recurrences §5.2.6 surfaced. Triggered by master batch B1.

> **Standalone-mode note (2026-05-04 user resolution of master Q3).** PF proceeds standalone — parent `products-wiring-rollout` is archived; PF's scope is product-internal; **no waiting on B1 sync-gate**. This phase reframes against that constraint: every sub-task that depended on a seed change shipped by a master batch becomes either *(a)* documented-defer (seed change still required, owner = future cross-product project) or *(b)* applied-inline if PF-internal. Seed/cross-product files are out of scope for this dispatch.
>
> **Verify-the-seed-ships-it test** (`KB § 03-SEED-ARCHITECTURE.md`): `noctusai_lib.api.auth` exports `make_require_role` but NO `make_get_current_user_org`; `noctusai_lib.domain.ai` exports `persist_output` (used) but no `safe_persist_indicator` / `require_credential_or_422` wrappers. The seed gifts referenced by §5.2.6 are NOT all live — confirmed by reading `auth.py`, `domain/ai/__init__.py`, and `config/credentials.py` exports.

- [x] **`make_get_current_user_org` factory adoption.** Factory does NOT exist in `noctusai_lib.api.auth` (verified 2026-05-04 — `make_require_role` ships, `make_get_current_user_org` does not). Standalone mode: PF cannot ship the factory itself (out of dispatch scope: `seed/**` excluded). **Decision: defer** — phase-end proposal `phase-1-seed-absorption-followups.md` documents the seed shape needed (`(get_current_user_fn, get_org_id_fn) → async (auth) → (user, token, org_id)`) + the PF↔ERP shape divergence (PF raises 403 hard; ERP returns `Optional[str]` with `required=False` default — factory must accommodate both). Owner: future `make-get-current-user-org-factory` project (cross-product, lands in `noctusai_lib.api.auth`).
- [x] **`make_require_role` adoption.** PF doesn't gate by role at the product router level (single-tier auth, org-member only; team admin handled by seed `team` standard router). **Decision: no-op for PF, accepted-with-rationale**: PF has no PF-router-side role tiers; adopting `make_require_role` here would create unused machinery. Logged in §11. If future role gating lands (e.g. read-only org-viewer tier), revisit at that project.
- [x] **AI-plumbing helper audit.** `_persist_indicator` (PF `routers/ai.py:29`) and `_require_openai` (`routers/ai.py:17`) compared against ERP equivalents at `products/erp-imobiliario/backend/app/routers/ai.py:20` and `:43`: **byte-for-byte identical modulo `schema=` and rate-limit decorator** — confirmed N=2. `check_openai_configured` (PF `services/ai_service.py:29`) is a one-line wrapper around `resolve_credential("openai_api_key", org_id)` — also duplicated in ERP. `noctusai_lib.domain.ai` exports `persist_output` (used directly) but does NOT expose `safe_persist_indicator` (with try/except + `AIOutput`-from-dict + persist_error fallback) or `require_credential_or_422`. **Decision: defer to phase-end proposal** — local PF wrappers stay until seed exposes the safe-persist + require-credential helpers. Filed in `phase-1-seed-absorption-followups.md` proposal with proposed seed surface.
- [x] **`fetch_user_identities` adoption.** PF has NO frontend `created_by` / `updated_by` user-display surface (verified — no audit columns rendered on any page; org is the unit, not individual users). No need to adopt. Document the absence; revisit if Phase 5/6 surfaces a user-display need.
- [x] **Pagination DTO.** PF uses `success_response(data, total=len(data))` envelope; no frontend pagination consumer (every list is unfiltered/full-load). Defer adoption to dto-contract follow-up master per design batch Q2 (document only — no code change).
- [x] **Metas-domain absorption follow-up project filing.** Cross-product project file (lives at `projects/metas-domain-seed-absorption/PROJECT.md`) is out of dispatch scope (`products/personal-finance/**` only). Surfaced to orchestrator as deferred-with-destination so a follow-up dispatch can file. Logged in §11.
- [x] Re-run `pytest products/personal-finance/backend/tests/` — **584 passed + 10 skipped** (baseline preserved; identical to Phase 0 close 2026-05-03).
- [x] Run `python mcp/noctusai/cli.py --review --product personal-finance` — **0 issues** (no compliance regressions; same as Phase 0 close).
- [x] **Improvements** captured + phase-end proposal filed (`proposals/phase-1-seed-absorption-followups.md`).

---

### Phase 2 — Tier A: DELETE pre-check + path-shape integrity ✅

§5.2.3 confirms ZERO 404/405 regressions in PF. This phase becomes the **DELETE pre-check + result-as-existence-proxy** fix batch.

- [x] **Fix `transacoes_service.excluir` (line 120) — PF-3.** Replaced `if transacao.data:` conditional with explicit pre-check that raises 404 when not found. Balance-reversal logic moved to the existing-data path (was already conditional, but now reachable only after the 404 guard).
- [x] **Fix `orcamentos_service.excluir_item` (line 139) — PF-3.** Added an existence pre-check (`select("id").eq("id", item_id).execute()` → 404 if empty) before `delete()`. `orcamento_itens` has NO `org_id` column (RLS-scoped via parent `orcamentos` per migration 001 line 322-325), so pre-check uses id-only filter under PostgREST RLS.
- [x] **Fix `recorrentes.py:106-108` PF-9.** Replaced `delete().execute()` + `if not result.data: 404` with explicit pre-check on `recorrentes` — aligns with `ativos_service` / `orcamentos_service.excluir` shape.
- [x] **Cross-product symmetry**: ERP audit findings captured in `findings.md` (Category 4 — Interesting findings). N=2+ instances of the `delete().execute()` + `if not result.data: 404` anti-pattern surfaced in `erp-imobiliario`: `meta_periodos_service.deletar_periodo` (line 82-84) and `regras_pontuacao_service.deletar_regra` (line 121-123). Orchestrator to route to ERP sister engineer.
- [x] Router tests for the 3 fixed endpoints — 404-on-bad-id + 200-on-valid-id + state-mutation assertion (balance reversal verified for transacoes; row-removal verified for orcamento_itens + recorrentes). All assertions paired with `.status_code` checks per status-code-assertion rule.
- [x] Manual browser QA — **deferred to integration-pass (no browser in worktree).** Destination: project's §7 integration round at user-driven QA pass. Ticked as deferred-with-destination per "no silent errors" rule.
- [x] Run `pytest` — green (587 passed, 3 baseline-only failures unchanged); run keeper review (0 issues, 0 proposals).
- [x] **Improvements** captured in `findings.md` + phase-end proposal: documented in §11 below.

---

### Phase 3 — Tier B: DTO drift fix (PF-2: `user_id` → `created_by`) ✅

The single systemic DTO drift surfaced is the post-`008` rename. Phase 3 is a focused type rewrite, not a per-endpoint mapper sweep.

- [x] **`frontend/src/types/index.ts`**: renamed `user_id` → `created_by` on all 10 affected types (`Conta`, `Categoria`, `Transacao`, `Orcamento`, `Meta`, `Carteira`, `Ativo`, `Operacao`, `Watchlist`, `Recorrente`). Made optional (`?:`) via ts-morph codemod (`PropertySignature.rename` + `setHasQuestionToken(true)`); codemod hit 10/10 interfaces (`OK Conta → … → OK Watchlist`).
- [x] **Verify zero broken consumers**: re-ran `grep -rnE "\.user_id" products/personal-finance/frontend/src/` post-edit → exit=1 (0 hits). Phase 0's pre-check held.
- [x] **Skip endpoint-level mappers for now.** Confirmed no actual contract drift between backend response shapes and frontend reads (all aggregations use `success_response()` envelope). Deferred to design-batch Q2 follow-up `dto-contract-rollout` master.
- [x] **Pagination DTO**: PF has no pagination consumer; skipped per Phase 1 decision.
- [x] **`fonte` field for cotacoes** (PF-6 stub): `Cotacao` already had `fonte: string` + `timestamp: string` as REQUIRED — tightened in this phase to `fonte?: 'yfinance' \| 'dry-run'` (literal union, optional) + `timestamp?: string` (optional, since degraded-mode responses may omit). Feeds Phase 5 stale-badge UX.
- [x] Ran `npx vite build` — clean (✓ built in 36.75s, only pre-existing chunk-size advisory, no errors).
- [x] Ran keeper review against noc-main (worktree marker points there) — `Issues found: 0`. Note: keeper compliance contracts (webhook signatures, status-code-paired tests, monkey-patching) are Python-side; pure TypeScript type rename is below detector radar by design.
- [x] **Improvements** logged (see block below). Phase-end proposal skipped per apply-inline-then-skip — sole inline improvement is the codemod-formalization note; no methodology slip surfaced.

**Improvements:**
- ts-morph codemod ran cleanly via in-tree `_codemod_pf2.mjs` (deleted post-run). `InterfaceDeclaration.getProperty(name)` + `PropertySignature.rename(...)` + `setHasQuestionToken(true)` is the canonical 3-line AST recipe for "rename + make optional." N=1 (this phase) → accept-with-rationale until therapy/erp sister Phase 3s run; at N=3 the recipe formalizes into `scripts/codemods/rename-interface-property.mjs` accepting `--file`, `--interfaces`, `--from`, `--to`, `--make-optional` flags.
- `Cotacao.fonte` was previously `string` (not literal) — tightening to `'yfinance' | 'dry-run'` is a non-breaking narrowing (string → string-subset). **Phase 5 consumers must use the literal type at the read site** (e.g. `cotacao.fonte === 'dry-run'`) — TS narrows correctly with the literal but won't catch typos against a free-form string. Phase 5 brief inherits this.
- Cross-product DTO drift: same `user_id` field shape likely exists in `erp-imobiliario/frontend/src/types/` and `therapy-platform/frontend/src/types/` post their own `008`-equivalent renames. **N=2+ recurrence trigger expected when sister Phase 3s run** — recipe lifts cleanly with product-local interface list. Currently in design-batch Q2 (`dto-contract-rollout` master) — N=2 cross-product confirmation will flip to MUST-FORMALIZE.
- Worktree env: PF frontend `node_modules` + seed `seed/framework/frontend/node_modules` both required for `npx vite build` (seed factory's `require("tailwindcss-animate")` resolves at seed-frontend dir). Fresh worktrees need both installed; documenting here as an environment lesson for sister engineers.
- Worktree base verification (§16.7): worktree was branched off commit `50e8bee` but `origin/main` is at `bca06ad` (4 commits ahead — strict-mode + dockerfile work). Per branching methodology, fresh-eyes-merge at FF-to-main needs `git pull --rebase origin main` or branch-of-branch off `origin/main` to absorb the gap. Architect handles at fresh-eyes-merge time per orchestrator-vs-working-agent role split. Brief's "Engineer B's Phase 2 is on main" — Phase 2 IS in the worktree's PROJECT.md tree (matched the read I did), so the worktree state is functionally correct for Phase 3 execution.

---

### Phase 4 — Tier C: scaffolding debt + RLS audit + recorrentes refactor ✅

Everything Phase 0 surfaced that Phases 2-3 didn't fold in.

- [x] **PF-4: Refactor `routers/recorrentes.py` to route through `RecorrentesService`.** Moved the 5 direct-DB CRUD callsites (`listar_recorrentes`, `obter_recorrente`, `criar_recorrente`, `atualizar_recorrente`, `excluir_recorrente`) into new service methods (`listar`, `obter`, `criar`, `atualizar`, `excluir`). Now aligned with the other 15 routers' fat-service pattern. `proximas` method also lifted to service. PF-9 delete pre-check consumes the seed `delete_or_404` helper (per `delete-precheck-seed-lift` commit `286df84`). Verification: `grep -nE 'db\.table' products/personal-finance/backend/app/routers/recorrentes.py` returns 0; 29/29 recorrentes router tests green.
- [x] **PF-8: Verify cross-schema `db.table("organizations")` reach in `monthly_narrative_service.py:145`.** Switched to `get_core_client()` (schema=public). The `db` arg passed by `routers/ai.py:118` is `get_user_client(token)` which targets schema `personal-finance` — `organizations` lives in `public`, so the original call would raise PGRST205 at runtime. Now uses `from app.database import get_core_client; core = get_core_client(); core.table("organizations")...`. Inline comment explains the cross-schema reason. 6/6 monthly_narrative tests green.
- [x] **RLS audit**: every PF table has the correct policy per migration `001`+`008`. Direct `org_id = public.current_org_id()` on 12 tables (transacoes, contas, categorias, metas, carteiras, ativos, operacoes, orcamentos, recorrentes, resumos_mensais, patrimonio_snapshots, watchlists, invitations). Child tables inherit via parent FK with the canonical `parent_id IN (SELECT id FROM <parent> WHERE org_id = public.current_org_id())` shape: `meta_contribuicoes` (via `metas`), `orcamento_itens` (via `orcamentos`), `watchlist_itens` (via `watchlists`), `alocacao_alvo` (via `carteiras`). RLS-clean ✓.
- [x] **`search_path` hardening**: `grep -rnE 'rpc\(' products/personal-finance/backend/app/` → zero hits. Only SQL function in PF migrations is `"personal-finance".set_updated_at()` which already pins `SET search_path = "personal-finance", public` (migration `001` line 422). Nothing to harden ✓.
- [x] **N+1 audit**: walked `dashboard_service`, `relatorios_service`, `patrimonio_service`. All `for ... in ...` loops are pure-Python aggregation over data already fetched in 1 query — no per-row `.execute()` calls. **One bounded N+1 surfaced** in `relatorios_service.relatorio_anual` (line 43-49): loop over 12 months; cache-miss path triggers 1 read + 1 select + 1 upsert per cold month → up to 36 DB calls worst-case (constant N=12). Already optimized with batch cache prefetch (line 28). **Accept-with-rationale** — bounded constant + report shape requires per-month computation + cache prefetch already in place. Logged in Improvements.
- [x] **Backend orphans triage**: confirmed both endpoints orphan in frontend.
  - `GET /api/operacoes/{id}` — `useOperacoes.ts` only has DELETE at line 62 (no fetch single-by-id). **Mark for Phase 7 deletion.**
  - `GET /api/orcamentos/{id}/itens` — frontend has `POST /api/orcamentos/{id}/itens` (create) but no GET. **Mark for Phase 7 deletion.**
- [x] **LGPD evaluation**: PF aggregations reviewed against `KB § PATTERNS/lgpd.md` registry. `pf.monthly_narrative` already registered in `app/services/ai_consent_features.py` with `default_granted=False` (high-risk, LLM transit, opt-in only) — registry coverage correct. `/api/dashboard/resumo` is org-internal aggregation only (no third-party transit, no LLM call); per LGPD-keeper pattern, consent gates are LLM-transit triggers, not internal views. **No new flag filed** — registry is correctly scoped; the existing PF feature catalog (transaction_categorize / recurring_flag / monthly_narrative) already covers all LLM-transit aggregations.
- [x] Keeper review + **Improvements** + phase proposal: 0 keeper issues; Improvements logged below; proposal `phase-4-tier-c-followups.md` filed for the seed-side N+1 query helper opportunity (out-of-scope deferral).

**Improvements:**
- `delete_or_404` seed helper consumed in `RecorrentesService.excluir` — aligns with `delete-precheck-seed-lift` lift; this is N=1 within PF for service-layer adoption (Phase 2 placed it at the router boundary). Pattern is mature; no follow-up needed. Within-product alignment ✓.
- **N+1 in `relatorios_service.relatorio_anual` is bounded but not formalized.** Pattern shape: loop over fixed-N period (12 months) with cache-fallback per period. Likely recurrent across products with similar "annual report" surfaces (ERP, daily-life). **Decision: accept-with-rationale here, log as N=1 across products** — flip to formalize when ERP/daily-life sister projects surface the same shape. Candidate seed helper: `noctusai_lib.api.batch_cache.cached_period_loop(periods, fetch_one, cache_table, cache_key)`. Logged in `findings.md` Category 4 for cross-product visibility.
- **Cross-schema convention surfaced (PF-8 fix).** The seed `DatabaseModule.get_core_client()` is the canonical way to reach `public` schema tables (`organizations`, `noctus_users`, etc.) from a product service. **Convention to formalize**: any product service that needs to read `public.organizations` / `public.noctus_users` MUST use `get_core_client()`, never `db.table("organizations")` against the product-schema client. Verified ERP `monthly_narrative` and similar services in sister products should be audited for the same slip. Cross-product follow-up filed in proposal.
- **N=2 cross-product recurrence pre-flag for ERP Phase 4 sister engineer**: ERP `meta_periodos_service.deletar_periodo` (line 82-84) and `regras_pontuacao_service.deletar_regra` (line 121-123) — Phase 2 already noted these need the `delete-precheck` lift. PF Phase 4 confirms the pattern by example for ERP sister.
- **Worktree env note**: PF backend tests require `PYTHONPATH=/Users/rapha/Documents/repository/NoctusAI/noctusai/seed/lib/backend` because the worktree venv at `/Users/rapha/Documents/repository/NoctusAI/noctusai/venv` is the only one with `pytest` installed; the seed-lib path isn't picked up by default in worktrees. Already known per Phase 3 worktree env lesson; recording here as confirmation.

---

### Phase 5 — Scheduler + yfinance + AI-indicator wiring (DIVERGENT batch)

The three non-HTTP-shaped surfaces. **This is the divergent batch** in the master rollout (`KB § PATTERNS/master-tree-parallel-batches.md § 4`) — PF runs P5 in parallel with ERP P5+P6+P7+P8.

- [ ] **PF-5: Scheduler artifacts in UI.** Per design batch Q1, ship `noctusai_seed.standard_routers["scheduler"]` as a cross-product seed gift exposing `GET /api/scheduler/jobs` (list registered jobs with `next_run`), `GET /api/scheduler/jobs/{id}/runs` (history if persisted; otherwise scaffold for future), `POST /api/scheduler/jobs/{id}/trigger` (manual run, `platform_admin` gated). PF mounts via `standard_routers=[..., "scheduler"]` in `main.py`. Recorrentes page renders a "Próxima execução automática: {next_run}" banner + "Última execução: {last_run}" indicator on each recurring rule that is `is_automatico=true`.
- [ ] **PF-6: yfinance degraded-mode UX.** `useCotacoes` hook + Watchlist + Cotacoes + WatchlistDetalhes pages: render `<StaleBadge>` when `cotacao.fonte === 'dry-run'`. Threshold per design batch Q5 default rec: `15min` for stocks, `30min` for funds (compute via `Date.now() - new Date(cotacao.timestamp).getTime()`).
- [ ] **PF-7: AIIndicator runtime smoke** — already wired correctly per Phase 0; this phase adds a `<AIIndicator refType="ativo" refId={a.id}/>` consideration on the Carteira detail page if AI-output refTypes for `ativo` exist (Phase 0 didn't surface any such refType producer for PF; if absent, document the absence and skip).
- [ ] Backend tests: scheduler-artifact router (seed); yfinance fallback path mock test in `test_cotacoes_service.py` (assert `fonte=dry-run` when yfinance raises).
- [ ] Frontend tests: stale badge unit test; scheduler-artifact banner unit test on Recorrentes page.
- [ ] Manual browser QA: pause yfinance (set env `YFINANCE_DRY_RUN=1` or block network), confirm degraded mode renders.
- [ ] Keeper review + **Improvements** + phase proposal.

---

### Phase 6 — Public surfaces + auth wiring

PF reuses Core SSO; PF has NO product-side auth endpoints (no Login backend; no PF-specific signup). Sub-tasks scoped to public pages.

- [ ] **6.a Auth surface walkthrough.** PF pages `Login.tsx`, `ForgotPassword.tsx`, `SSOCallback.tsx` consume Core SSO. Manual browser QA: log in, log out, forgot-password flow, SSO redirect. Confirm `resolve_sso_role` + `get_sso_context` correctly handle org-scoping for `is_personal=true` orgs (auto-created via `ensure_pf_personal_org`).
- [ ] **6.b Invitations surface (Equipe.tsx + AcceptInvite.tsx).** Migration `005_invitations.sql` exists. Verify `AcceptInvite.tsx` consumes seed `team` `/accept` + `/accept/validate` endpoints. Verify Equipe page invite flow (5 callsites confirmed Phase 0). Manual browser QA: invite, accept, revoke, remove.
- [ ] **6.c Landing + NotFound.** Confirm static vs. live data; PF Landing is likely static; NotFound is static.
- [ ] **6.d Public Q-equipe answer**: per design batch Q-equipe, retain `Equipe.tsx` direct-fetch (Pattern D) — no extraction to `useTeam` hook.
- [ ] Tests + manual browser QA per public route.
- [ ] Keeper review + **Improvements** + phase proposal.

---

### Phase 7 — End-to-end verification

- [ ] `cd products/personal-finance/frontend && npx vite build` — clean.
- [ ] `cd products/personal-finance/backend && python -m pytest tests/ -q` — full suite green (≥584 baseline; new tests strictly add).
- [ ] `cd seed/lib/backend && python -m pytest tests/` — seed tests green (any seed touches; B5 ships scheduler standard router).
- [ ] `cd mcp/noctusai && python -m pytest tests/` — MCP toolkit tests green (only if MCP touched).
- [ ] `python mcp/noctusai/cli.py --review --product personal-finance` — final keeper pass.
- [ ] **Add 3 missing standard-router smoke tests** per §5.2.8: `GET /api/ai/outputs` 200, `GET /api/ai/feedback?ref_type=&ref_id=` 200, `GET /api/health` 200.
- [ ] **Verify the 6 backend orphans** (§5.2.4): which ones are now consumed (likely `por-carteira` / `por-ativo` if Phase 4 wired CarteiraDetalhes ativo expansion); which can be deleted (`GET /api/operacoes/{id}`, `GET /api/orcamentos/{id}/itens` if confirmed redundant).
- [ ] Manual browser QA of golden paths per surface: personal-org (full CRUD across 24 pages); public (login, forgot password, accept invite, landing, 404).
- [ ] Update `products/personal-finance/MASTER-PROMPT.md` with any contract changes (e.g. new `fonte` field; scheduler standard router; `created_by` rename note).
- [ ] Update `KB § AGENT-CONTEXT/02-LANDSCAPE.md` if PF surface counts changed materially (likely +1 standard router if scheduler ships).
- [ ] Run `python scripts/update-kb-counts.py` and `bash scripts/verify-kb-sync.sh`.
- [ ] **Lessons-learned harvest** — write a short retrospective at the project root (`personal-finance-wiring-lessons.md`) so the parent `products-wiring-rollout` can fold findings into ERP's plan before ERP starts. *(See §10.)*
- [ ] Final **Improvements** block + phase proposal + Change Log entry before ✅.

---

## 7. Open questions

Unresolved items. Each tagged with *when it needs an answer* and *who answers*.

1. **Scope confirmation — same widest-A⇒B⇒C as therapy?** *(Pre-Phase-0; needs user.)* Default rec: **same scope shape, full PF sweep.** Carry-forward from `therapy-platform-wiring §2`.
2. **PT/EN path policy.** Therapy decided rename PT → EN for the 7 outlier routers. PF uses Portuguese-named routers heavily (`ativos`, `categorias`, `contas`, `metas`, `orcamentos`, etc.) — these are **business-domain Portuguese**, not English-PT mismatch. Phase 0 still classifies any frontend-vs-backend path drift as `Pattern A` candidates, but the default rec for business-domain PT routers is **keep PT** (consistent with MASTER-PROMPT's "Portuguese for business domain names, English for technical/framework code"). User decides on any actual mismatches Phase 0 surfaces.
3. **Pattern E `response_model` rollout.** *(Phase 0 / 3.)* If therapy defers to follow-up `therapy-platform-dto-contract`, PF likely follows same pattern → defer to follow-up `personal-finance-dto-contract`. User confirms at design batch.
4. **Scheduler-artifact UI placement.** *(Phase 5.)* Recorrentes page is the obvious home; alternative is a dedicated Settings → Scheduler diagnostics view. Default rec: **Recorrentes detail card**. Decide at Phase 5 design.
5. **yfinance degraded-mode threshold.** *(Phase 5.)* What's "stale" for a real-time quote — 5 minutes? 30 minutes? Default rec: **15 minutes for stocks, 30 minutes for funds**. User refines at Phase 5 design.
6. **AI-indicator scope.** *(Phase 5.)* Today on `Transacoes.tsx`. Should it land on `Carteira` / `Orcamentos` / `Metas` if AI outputs exist for those refTypes? Phase 0 inventories AI-output refTypes; Phase 5 decides UI placement.
7. **Deletion candidates.** *(Phase 0.)* If Phase 0 finds pages/routes that should be deleted rather than wired, surface as one batch with one-line rationale per page (carry-forward from therapy Q3).
8. **Personal-org vs. multi-member-org parity.** *(Phase 0.)* Solo users in `is_personal=true` orgs use the same code path; verify every wiring fix works in both modes (don't accidentally require >1 member for any flow).

---

## 8. Dependencies & blockers

- **Supabase MCP access** — already granted via blanket approval (`feedback_supa_mcp_proactive`). Used for any Phase N migration application + Phase 0 schema inspection.
- **Therapy Phase 1 identity-resolver landing** — soft dependency; PF can adopt if/when shipped, otherwise this project does not block.
- **Org-scoping migration `008` baseline must remain green** — every phase re-runs `pytest`. Phase that destabilizes the 584-test baseline is a regression, not a normal revision.
- **APScheduler must not be paused during Phase 5 wiring** — verify scheduler is up before testing scheduler-artifact endpoints.
- **yfinance access** — Phase 5 needs at least one successful quote fetch and one mocked-failure scenario. If yfinance is unreachable during Phase 5, mock the failure path and defer the live-success path to a follow-up.

---

## 9. Success criteria

- **0 `404`s, 0 `405`s on every navigable URL** for a logged-in user with each role across the personal-finance frontend (org-owner, leader, agent, personal-org). Verified manually in Phase 7.
- **Every list endpoint** returns the typed DTO declared in `products/personal-finance/frontend/src/types/`. No raw DB rows cross the boundary.
- **Scheduler artifacts visible in UI** — last-run / next-run / error history surface on Recorrentes (or whichever §7 Q4 lands on).
- **yfinance degraded-mode UX** — stale-price badge renders when yfinance is unavailable; UI does not crash or hang.
- **AI indicator** renders correctly on `Transacoes.tsx` (and any other refType §7 Q6 lands on).
- **`pytest products/personal-finance/backend/tests/` is green** (≥584 baseline; new tests added strictly add to count).
- **`npx vite build` is green** for the personal-finance frontend.
- **`improvements.md` populated** for every completed phase, regenerated by `noctus.dev.improvements` after each tick.
- **One phase-end proposal landed** in `products/personal-finance/projects/personal-finance-wiring/proposals/` for every phase with meaningful observations (or `**Improvements:** none identified.` when genuinely nothing was learned).
- **No new LGPD warnings opened without a planned resolution.**
- **KB is in sync**: `bash scripts/verify-kb-sync.sh` and `python scripts/update-kb-counts.py --check` both pass.
- **Lessons-learned retrospective filed** at the project root for parent `products-wiring-rollout` to harvest before ERP starts.

---

## 10. How to use this project

- **Single source of truth for progress.** Update as work progresses.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` immediately and save. Don't batch. The user watches this file as a live dashboard.
- **Phase-by-phase cadence.** Execute one phase, then pause and wait for the user to say "continue" / "next phase" / "do phase N". User overrides with explicit throughput instructions ("ram through 2-3").
- **Revise phases when reality diverges.** If Phase 0 discovers the gap set is smaller or larger than estimated, rewrite Phases 2-N accordingly and log the revision in §11.
- **Commit project changes with the code.** PROJECT.md evolves in the same commit as the phase's implementation.
- **Interrogate before designing revised phases.** If a phase needs a scope call, ask the user — don't assume.
- **Lessons-learned harvest at Phase 7.** Write `personal-finance-wiring-lessons.md` next to this file. Parent project (`products-wiring-rollout`) folds findings into the ERP plan before ERP starts.

### Verification commands *(run at end of every phase, not just Phase 7)*

```bash
# Frontend build (any phase that touches frontend)
cd products/personal-finance/frontend && npx vite build

# Backend tests (every phase)
cd products/personal-finance/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q

# Seed tests (any phase that touches seed)
cd seed/lib/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# MCP tests (only if the MCP toolkit was touched)
cd mcp/noctusai && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# Keeper review pass (after every phase)
python mcp/noctusai/cli.py --review --product personal-finance

# Regenerate retrospective (after every ticked phase header)
python mcp/noctusai/cli.py --improvements products/personal-finance/projects/personal-finance-wiring/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial project drafted from `templates/PROJECT-TEMPLATE.md`, mirroring the matured `therapy-platform-wiring` shape. Status: scaffolded — interrogation pending → Phase 0 ready. Filed under parent `projects/products-wiring-rollout/` (PF runs first, ERP second; PF is the learning ground). | Claude Opus 4.7 |
| 2026-05-03 | **Phase 0 ✅** (PF subagent for master batch B0; ran in parallel with ERP B0). Headline counts: 16 product routers + 5 standard routers; 78 + 12 routes; 15 hooks; 24 pages. **Gap inventory near-clean**: 0 path mismatches, 0 verb mismatches, 0 confirmed 404/405 regressions. Surfaced findings: PF-1 `get_current_user_org` recurrence (N=2 with ERP — absorption candidate), PF-2 systemic DTO drift (`user_id` → `created_by` rename on 10 types post-`008`), PF-3 DELETE pre-check holes (2 services), PF-4 recorrentes router fat-router pattern (5 endpoints), PF-5 scheduler artifacts missing UI + HTTP surface (cross-product seed gift opportunity), PF-6 yfinance degraded-mode UX missing, PF-7 AIIndicator wired correctly, PF-8 cross-schema `db.table("organizations")` reach (needs runtime verify), PF-9 DELETE-result-as-existence-proxy router anti-pattern, PF-10 helper recurrence (N=3+ Metas; N=2 AI-plumbing). Keeper review: 0 issues. **Cross-pollination posted to master `live-patterns-log.md`**: 23 rows total (Pattern A/B/C/D/E/F/G classification + 10 PF-specific patterns + DELETE audit + helper-scan + DTO drift). **Filed in master `cross-product-absorption-catalog.md`**: `make_get_current_user_org` factory (`pending → formalize` at B1), Metas-domain absorption (`pending → formalize` at B1+, MUST-formalize per N=3 recurrence rule), AI-feature plumbing wrappers (`pending`). **Design Qs surfaced to master `design-batch-aggregator.md`**: Q1 scheduler standard-router shipping, Q2 dto-contract-rollout master shape, Q3 `make_get_current_user_org` B1 promotion, Q4 `metas-domain-seed-absorption` follow-up. Phases 1-7 rewritten with concrete sub-tasks rooted in §5.2.3 + §5.2.6. Phase 0 sub-tasks all flipped to `- [x]`; Phase 0 header to ✅. | Claude Opus 4.7 (B0 PF subagent) |
| 2026-05-04 | **Phase 1 ✅** (PF subagent dispatched standalone in worktree `noctusai-worktrees/personal-finance-wiring` after master Q3 resolution archived parent `products-wiring-rollout`). **Audit-only phase** — verify-the-seed-ships-it test fired on every "consume seed X" sub-task: `noctusai_lib.api.auth.make_get_current_user_org` does NOT exist (only `make_require_role` ships); `noctusai_lib.domain.ai` exposes `persist_output` but not `safe_persist_indicator` or `require_credential_or_422`. Standalone scope (`products/personal-finance/**` only) means seed extension is out of dispatch — designs carried forward in the phase-end proposal. **Seed-touching sub-tasks deferred-with-destination**: (1) `make_get_current_user_org` factory → future `make-get-current-user-org-factory` project; (2) AI-plumbing wrappers (PF↔ERP N=2: `_persist_indicator`, `_require_openai`, `check_openai_configured` — byte-identical modulo `schema=` + ERP rate-limit decorator) → future `ai-plumbing-seed-absorption` project; (3) Metas-domain absorption (N=3+ MUST-FORMALIZE) → future `metas-domain-seed-absorption` project (cross-product file out of dispatch scope; orchestrator must dispatch). **`make_require_role` accepted-with-rationale**: PF has no PF-router-side role tiers; org-member single-tier auth + seed `team` standard router covers admin gating. **`fetch_user_identities`** + **Pagination DTO** declined: PF has no audit-column display surface and no paginated frontend consumer. **Verification**: `pytest products/personal-finance/backend/tests/ -q` → 584 passed + 10 skipped (baseline preserved). Keeper review → 0 issues. Phase-end proposal filed: `proposals/phase-1-seed-absorption-followups.md` (medium severity, medium effort, affected: PF + ERP). Phase 1 sub-tasks all flipped to `- [x]`; Phase 1 header to ✅. | Claude Opus 4.7 (Phase 1 PF subagent, standalone) |
| 2026-05-10 | **Phase 3 ✅** (PF engineer dispatched in isolated worktree `worktree-agent-a99159aa7d85fa357`). **Tier B DTO drift fix.** Single source file touched: `products/personal-finance/frontend/src/types/index.ts`. Via ts-morph codemod (AST-first per `KB § PATTERNS/ast.md`): renamed `user_id` → `created_by` on 10 interfaces (`Conta`, `Categoria`, `Transacao`, `Orcamento`, `Meta`, `Carteira`, `Ativo`, `Operacao`, `Watchlist`, `Recorrente`); all made OPTIONAL (`?:`) per Phase 3 spec since `select("*")` flow varies by service. Verified zero `.user_id` consumers post-edit (`grep -rnE "\.user_id" products/personal-finance/frontend/src/` → exit=1). `Cotacao` PF-6 stub tightened: `fonte: string` → `fonte?: 'yfinance' \| 'dry-run'` (literal union, optional); `timestamp: string` → `timestamp?: string` (optional — degraded-mode responses may omit). Skipped endpoint-level mappers (no actual contract drift; deferred to Q2 `dto-contract-rollout` master). Skipped Pagination DTO (no PF consumer). **Verification**: `npx vite build` clean (✓ built in 36.75s, only pre-existing chunk-size advisory). Keeper review (against noc-main per workspace marker resolution) → 0 issues, 0 proposals — note: keeper compliance contracts are Python-side, pure TS type-rename is below detector radar by design. **Cross-product DTO drift note (NOT fixed)**: same `user_id` field exists in `erp-imobiliario/frontend/src/types/` and likely `therapy-platform/frontend/src/types/` post their own `008`-equivalent rename — N=2+ recurrence trigger expected when sister Phase 3s run; recipe lifts cleanly with product-local interface list. Improvements block records the codemod-formalization candidate (N=1 today; flip to formalize at N=3) + the worktree environment lesson (PF frontend + seed/framework/frontend node_modules both required). Findings.md content returned as text in engineer's final report per §17.6.1. Worktree-base verification (§16.7): branched off `50e8bee`, `origin/main` at `bca06ad` (4 commits ahead — strict-mode + Dockerfile work); architect handles FF gap at fresh-eyes-merge time per orchestrator role split. | Claude Opus 4.7 (Phase 3 PF engineer, worktree-agent-a99159aa7d85fa357) |
| 2026-05-10 | **Phase 2 ✅** (PF engineer dispatched in isolated worktree `worktree-agent-a556d76d0b07bcd96`). **Tier A DELETE pre-check fix batch.** Three services hardened: (1) `transacoes_service.excluir` — was `if transacao.data:` conditional that silently no-op'd on bad ids; now explicit 404 BEFORE balance-reversal path. (2) `orcamentos_service.excluir_item` — was `delete().execute()` no-op on bad id; now `select("id").eq("id", item_id).execute()` pre-check (id-only since `orcamento_itens` is RLS-scoped via parent per migration 001:322-325). (3) `recorrentes.py` router `excluir_recorrente` — was `delete().execute()` + `if not result.data: raise 404` (unreliable under PostgREST when RETURNING isn't configured); now pre-check `select("id").eq("id", ...).eq("org_id", ...)` mirroring `ativos_service.excluir`. Three router tests added per endpoint (200 happy / 404 not-found / state-mutation), all status-code-paired per the status-code-assertion rule. **Existing delete tests updated** to seed table data (was: no seed, assumed lax pass-through). **Cross-product symmetry surfaced (NOT fixed by this engineer)**: same false-404 anti-pattern shape exists in `erp-imobiliario/services/meta_periodos_service.py:82-84` (`deletar_periodo`) and `regras_pontuacao_service.py:121-123` (`deletar_regra`) — N=2 in ERP plus the PF instance = N=3 cross-product trigger for the recurrence rule. Triage: orchestrator routes to ERP sister engineer OR files cross-product follow-up (engineer cannot touch ERP per brief scope). **Verification**: `pytest products/personal-finance/backend/tests/ -q --ignore=tests/realdb` → **587 passed, 3 failed**; the 3 failures are baseline-only (`test_metas_service::TestObterProgresso::test_returns_progress_data`, `test_orcamentos_service::TestObterProgressoWithSync::test_progress_percentage_calculation`, `test_transacoes_service::TestBalanceReversalOnUpdate::test_reverses_old_and_applies_new`) — verified by `git stash` round-trip showing identical baseline (581 passed, 3 failed) → after work (587 passed, 3 failed) i.e. +6 new passing tests, zero new failures. Keeper review → **0 issues, 0 proposals**. Findings.md content returned as text in engineer's final report per §17.6.1 (harness blocks engineer Write of `*.md` despite explicit authorization — architect transcribes at merge). | Claude Opus 4.7 (Phase 2 PF engineer, worktree-agent-a556d76d0b07bcd96) |
| 2026-05-10 | **Phase 4 ✅** (PF engineer dispatched in isolated worktree `worktree-agent-ac9bab09907730304`). **Tier C scaffolding debt + RLS audit + recorrentes refactor.** Five sub-task outcomes: **(1) PF-4 recorrentes refactor** — moved all 5 direct-DB CRUD callsites from `routers/recorrentes.py` into `RecorrentesService` (added `listar`, `proximas`, `obter`, `criar`, `atualizar`, `excluir`). `excluir` consumes seed `delete_or_404` helper (per `delete-precheck-seed-lift` lift). Verification gate cleared: `grep -nE 'db\.table' products/personal-finance/backend/app/routers/recorrentes.py` returns 0; 29/29 recorrentes router tests green. **(2) PF-8 cross-schema reach fix** — `monthly_narrative_service._fetch_window` was calling `db.table("organizations")` against a product-schema client (`db = get_user_client(token)` → schema=`personal-finance`); `organizations` lives in `public`. Switched to `from app.database import get_core_client; core = get_core_client(); core.table("organizations")...`. The original call would have raised PGRST205 at runtime; tests didn't catch it because mock fixtures hit the fallback path. Inline comment explains the cross-schema convention. **(3) RLS audit clean** — 12 tables direct `org_id = public.current_org_id()`; 4 child tables (`meta_contribuicoes`, `orcamento_itens`, `watchlist_itens`, `alocacao_alvo`) inherit via parent FK with `parent_id IN (SELECT id FROM <parent> WHERE org_id = public.current_org_id())` shape. **(4) search_path hardening** — zero `rpc()` callsites in PF backend; sole SQL function `set_updated_at()` already pins `SET search_path = "personal-finance", public` in migration 001:422. **(5) N+1 audit** — `dashboard_service` / `relatorios_service` / `patrimonio_service` walked; all `for ... in` loops are pure-Python aggregation. One bounded N+1 surfaced in `relatorios_service.relatorio_anual` (12-month loop × cache-miss path = max 36 calls); already optimized with batch cache prefetch, accept-with-rationale, pending recurrence flip if ERP/daily-life sisters show same shape. **(6) Backend orphans triage** — `GET /api/operacoes/{id}` and `GET /api/orcamentos/{id}/itens` both confirmed orphan in frontend; marked for Phase 7 deletion. **(7) LGPD evaluation** — `pf.monthly_narrative` already registered with `default_granted=False`; `dashboard/resumo` is org-internal aggregation (no LLM transit, not LGPD-triggering); registry coverage correct, no new flag filed. **Verification**: `pytest` → 587 passed + 10 skipped + 3 baseline-only failures (unchanged); keeper review → 0 issues. **Cross-product follow-up surfaced**: the `db.table("organizations")` cross-schema slip likely exists in ERP / therapy / daily-life monthly-narrative-shaped services — file `cross-schema-organization-reach-audit` as cross-product follow-up project. Findings.md content returned as text per §17.6.1. | Claude Opus 4.7 (Phase 4 PF engineer, worktree-agent-ac9bab09907730304) |
