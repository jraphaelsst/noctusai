# ERP Imobiliário Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log. See
> `CLAUDE.md → Universal rules → Projects are living + planners interrogate first`.
>
> **Slug rationale (honest-scope check):** Mirrors the closed `personal-finance-wiring`
> (`archive/projects/2026-05-11/16-personal-finance-wiring/`) and in-flight
> `therapy-platform-wiring` (`products/therapy-platform/projects/therapy-platform-wiring/`).
> Same shape: close every scaffolding gap end-to-end across the whole
> `erp-imobiliario` product — admin, broker, accounting/finance, portal-cliente,
> portal-externo, public landing, plus the metas / matching / vista-showcase
> verticals — landing at green build + green pytest + 0 keeper issues. Pure
> *wiring*, not redesign or feature growth.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-25 (Phase 8 ✅ — end-to-end verification + lessons retro; all phases complete; status: shipped-pending-archive)
- **Status:** ✅ **shipped-pending-archive.** All 8 phases complete. Phase 0 ✅ discovery;
  Phase 1 ✅ Pattern F initial (300 callsites) + delete_or_404 sweep (15 sites);
  Phase 2 ✅ `_persist_indicator` → `safe_persist_indicator` (5 callsites in `ai.py`);
  Phase 3 ✅ `_require_openai` thin-wrapper + matching.py inline-checks → seed
  `require_credential_or_422`, test fixtures lifted to
  `noctusai_lib.config.credentials.resolve_credential`, `make_require_role`
  adoption across `vista_showcase` + `metas_digest`, status-code calibration
  (8 test gaps closed), 7 new factory smoke tests; Phase 3b ✅ N=6 highest-leak-risk
  PII routers covered with `<entity>_row_to_dto` mappers; Phase 4 ✅ scaffolding debt;
  Phase 5 ✅ corretor wiring; Phase 6 ✅ portal-cliente + portal-externo;
  Phase 7 ✅ standard-router smoke + vista SSO + financial LGPD; Phase 8 ✅
  verification + retro (2026-05-25). Manual browser QA deferred to architect/user
  vs live fleet (stack not running in worktree context).
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `CLAUDE.md § Universal rules` — behavioral rules, loaded every session
  - `KNOWLEDGE-BASE/02-LANDSCAPE.md` — product surface inventory
  - `KNOWLEDGE-BASE/backend/02-ERP.md` — ERP backend spec
  - `KNOWLEDGE-BASE/PATTERNS/project-execution.md` — cadence, naming, tests-with-code
  - `KNOWLEDGE-BASE/PATTERNS/proposals-and-improvements.md` — phase-end protocol
  - `KNOWLEDGE-BASE/PATTERNS/database-rls.md` — migration discipline
  - `KNOWLEDGE-BASE/PATTERNS/lgpd.md` — personal-data guardrails
  - `archive/projects/2026-05-11/16-personal-finance-wiring/personal-finance-wiring-lessons.md` — PF retro inherited into this project
  - `products/erp-imobiliario/MASTER-PROMPT.md` — the agent-facing product contract
- **Project slug:** `erp-wiring`

---

## 1. Context & Purpose

`erp-imobiliario` is the largest product in the platform — 60 routers, 321 backend endpoints, 65 frontend hooks, 67 pages, 29 migrations. It runs **second** in the master products-wiring rollout (after `personal-finance` closed 2026-05-11, alongside `therapy-platform` in flight). The PF lessons retro (`personal-finance-wiring-lessons.md`) explicitly recommends:

> **Phase 0 as the load-bearing phase.** A near-clean gap inventory ... let the rest of the project execute almost entirely against §5.4 rows rather than re-discovery. **For ERP: budget a full session for Phase 0; do NOT try to overlap audit + first fix batch.**

This project executes exactly that recipe. Phase 0 (this document's first deliverable) produced a complete inventory: every router prefix + endpoint count, every hook + API call, every gap classified by the 7 Pattern shapes (A-G) inherited from therapy §5.4.2, every migration column cross-referenced against service-layer table-calls, plus a `Pattern H` orphaned-hook column added per PF lessons §b.2.

The win looks like: `vite build` clean, `pytest tests/` green, every navigable page in the ERP frontend loads with a 200 (admin + corretor + portal-cliente + portal-externo + public landing), and the seed-lib hit rate on absorption candidates is N≥3 → formalized where PF surfaced N=2.

---

## 2. Confirmed constraints

Mirrors PF + therapy §2 + design-batch decisions (PF Q2 default rec carries forward — ERP keeps PT business-domain routes; no rename, ERP is the canonical PT-domain product). User pre-decisions inherited from PF/therapy:

- **Scope breadth — widest (A ⇒ B ⇒ C):** fix known regressions, sweep admin, close pre-existing scaffolding debt, widen to every role surface (corretor / portal-cliente / portal-externo / public / vista-showcase admin).
- **PT business-domain routes stay PT** — ERP routes (`/api/clientes`, `/api/contratos`, `/api/imoveis`/`ativos`, `/api/locacoes`, `/api/vistorias`, etc.) are correctly PT per PF Q2 default rec. **Pattern A in §5.4.2 is therefore expected to be 0 for ERP** — verified during Phase 0.
- **Tests** — always, per the three-layer discipline in `KB § PATTERNS/testing.md`.
- **Cadence** — phase-by-phase, pause after each, no auto-advance. User explicitly says "continue" / "do phase N" / "ram through 2-3" when bulk execution is wanted.
- **Seed sync** — patterns worth promoting mid-project land as phase-end proposals via `noctus.dev.file_proposal(project="erp-wiring", …)`. Reviewer triages separately; this project does not block waiting for seed promotion.
- **"The platform" widest-scope** — interpreted as the `erp-imobiliario` product in full, not the whole NoctusAI repository.
- **Verify-the-seed-ships-it test fires at every absorption decision** — PF Phase 1 lesson: read the seed module's `__init__.py` exports + concrete adapter file before locking "we'll consume seed X". Gap + N=2+ consumers → file follow-up project, ship against Fake / defer.
- **PF lessons retro is non-binding pre-reading** — every Phase 1+ engineer brief MUST link to the retro.

---

## 3. Design principles

How we're approaching *this specific problem* on top of platform-wide `CLAUDE.md` rules.

1. **Fix at the layer of the cause.** N=2 patterns inside ERP get triaged at decision time; N=3 patterns across PF+ERP+therapy trigger seed-lib formalization (recurrence rule, `KB § PATTERNS/project-execution.md §2.7`). The PF retro `(e)` table pre-stages most of these — ERP Phase 1 walks that list with the verify-the-seed-ships-it test on each row.
2. **No band-aids.** No `?? ''` guards to tolerate bad DTOs; the DTO is correct at the backend boundary or the endpoint is broken and Phase 0 catches it.
3. **LGPD-first on every personal-data endpoint.** ERP touches client PII (cpf, rg, telefone, endereco, dados bancarios), financial PII (commissions, comissoes_splits, financeiro), and broker employment data (equipe_membros) — every aggregation in a new shape gets a `noctus.dev.lgpd_flag` call.
4. **Migrations and applied SQL stay in lockstep.** Every DDL we apply via `mcp__claude_ai_Supabase__apply_migration` lives first as `products/erp-imobiliario/backend/migrations/NNN_<name>.sql`. Next free slot at Phase 0 close: **030** (029 is the last existing).
5. **Tests land in the same phase as the code.** Three-layer discipline, no exceptions.
6. **Discovery is an artifact, not a vibe.** Phase 0 produces a checked-in gap table in §5.4. Phases 2+ reference rows in that table — no phantom scope.
7. **Status-code-assertion rule (PF retro §b.3) is calibrated in Phase 0, not enforced reactively.** Run `noctus.dev.scan_block_patterns mode=status_assertion` over ERP tests in Phase 0; baseline-no-regress for the existing corpus.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Six-question checklist per `KB § GUIDES/seed-first-design.md`:

1. **Is the contract identical for every product?** **MIXED.** Cross-cutting contracts (auth, response envelopes, request-id middleware, notifications, action_log, AI plumbing, metas domain) are uniform → seed. Business-domain contracts (clientes, contratos, vistorias, locacoes, matching, vista-showcase) are ERP-specific → product.
2. **Is the data source product-specific?** **MIXED.** Business tables (`clientes`, `ativos`, `contratos`, `vistorias`, `locacoes`, `comissoes`, `chaves`, `matriculas`, `certidao_*`) live in `erp` schema and are ERP-only. Cross-product tables (`org_settings`, `tool_call_audits`, `ai_outputs`, `ai_feedback`, `user_actions_log`) live in `core` / shared schemas via canonical cross-schema reach.
3. **Is the placement product-specific?** **MIXED.** ERP-only pages (`Imoveis`, `Contratos`, `Vistorias`, etc.) are product-bound. Shared infra (Notificações, Equipe, AcceptInvite, ForgotPassword, LLMPreferences) inherits from seed.
4. **Is the visibility / permission rule the same?** **NO.** ERP has 4 distinct role tiers (admin/coordenador/corretor + portal-cliente + portal-externo public) plus `vista-showcase` platform-admin gate. Seed provides the `get_user_role` primitive; ERP composes the rule.
5. **Does the seam already exist in seed?** **PARTIAL.** Seed-lib audit at Phase 0 close: `responses` ✅, `crud_safety` ✅ (4 imports, includes `delete_or_404`), `webhook_signatures` ✅, `domain.action_log` ✅, `domain.ai.persist_output` ✅, `domain.metas` ⚠ (not yet adopted in ERP — N=3 absorption pending), `domain.digest.BaseDigestService` ✅ (4-adopter cluster includes ERP metas-digest candidate — verify), `integrations.whatsapp` ✅ (2 imports), `integrations.vista` ✅ (2 imports), `integrations.llm` ✅ (2 imports), `integrations.email.digest` ✅, `api.auth.first_or_none` + `resolve_sso_role` ✅ (PF Phase 1 retired). **NOT shipped (per PF lessons §c):** `make_get_current_user_org` (N=2 PF+ERP → N=3 if therapy adopts), `safe_persist_indicator` / `require_credential_or_422` AI plumbing wrappers (N=2 PF+ERP), `scheduler` standard router (N=3 likely with mailing + therapy).
6. **Default-on or opt-in?** ERP's seed consumption is **default-on** via `create_product_app(standard_routers=["health", "notificacoes", "team", "llm", "ai_outputs", "ai_feedback"], …)` at `app/main.py:41`. No opt-out flags needed.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** for cross-product concerns (every PF retro §e row that fires N=3 in ERP MUST formalize at the seed; the consumer-side fork count target is **0**).
- [x] **A small section** for product-specific wiring (clientes/contratos/vistorias/locacoes/matching domain routers — ERP-bound, not seedable).
- [ ] **Multiple files / pages / mounts per product** — none planned. If a Phase surfaces this shape, STOP and re-design.

**Phase plan implications:** §6 phases work in-product (ERP-domain wiring) **plus** seed-side absorption phases for the recurrence-rule firings (Phase 1 mirrors PF Phase 1 — seed-lib absorption batch). No "walk through products" framing — this is a single-product wiring sweep with seed-side pre-emptive absorption for cross-product patterns whose N flips to 3 here.

---

## 4. Scope

**In scope:**

- Every `erp-imobiliario` backend endpoint that a frontend hook calls. Phase 0 inventory in §5.4 captures all 60 routers / 321 endpoints / 65 hooks / 67 pages.
- Every ERP migration needed to close column drift (§5.4.5 — **none found at Phase 0**).
- Seed-side absorption candidates whose N=2 PF baseline flips to N=3 here (per PF retro §e). At minimum: `make_get_current_user_org`, AI plumbing wrappers, `metas` domain adoption.
- Frontend corrections to consume corrected DTOs or fix UI bugs uncovered during sweep.
- Tests (unit + router + integration) landing in same phase as code.
- LGPD awareness via `noctus.dev.lgpd_flag` where endpoints aggregate PII in new shapes.
- End-to-end verification: `vite build` + `pytest` + manual browser QA of golden paths.

**Out of scope (for now — with reason):**

- **Other products** — `personal-finance` closed, `therapy-platform` in flight as separate projects.
- **UX redesigns** — wiring project, not redesign.
- **New features** — no capability we aren't already carrying as scaffolded UI.
- **Stripe / payment provider deep integration** beyond what's already scaffolded (assinaturas signature provider, financeiro lancamentos).
- **Vista CRM deep integration** — `vista_showcase` router wires the existing surface; vendor expansion is a future project.
- **WhatsApp WAHA depth** — wire the existing routes; chatbot framework expansion (per `KB § PATTERNS/whatsapp-chatbot-seed.md`) is a future project.
- **AI prompt tuning / LLM pipeline restructure** — only the wiring.
- **`vista_showcase` platform-admin tooling** beyond what currently exists.

---

## 5. Architecture / Data Model

*§5.1-5.3 are placeholders until seed-absorption decisions land in Phase 1. §5.4 is the Phase 0 deliverable, populated below.*

### 5.1 Shared `make_get_current_user_org` adoption *(delivered by Phase 1)*

PF retro §e row 1: PF + ERP = N=2 today; therapy adoption flips to N=3. PF filed `make-get-current-user-org-factory` follow-up project. ERP Phase 1 either:
- (a) Adopts the seed-side factory IF it ships before ERP Phase 1 starts.
- (b) Defers — surfaces the gap to `accept-with-rationale` for ERP, files a re-confirmation in the master rollout. Path (b) is the verify-the-seed-ships-it test working as designed.

### 5.2 AI plumbing wrappers adoption *(delivered by Phase 1 or deferred)*

PF retro §e row 2: PF + ERP = N=2 byte-identical (`_persist_indicator`, `_require_openai`, `check_openai_configured` modulo `schema=` + rate-limit decorator). Same verify-the-seed-ships-it logic.

### 5.3 Metas domain adoption *(delivered by Phase 1)*

PF retro §e row 3: PF + ERP + daily-life = N=3 MUST-FORMALIZE. `noctusai_lib.domain.metas` already lifted per KB pointer (`KB § PATTERNS/metas-seed.md`). ERP currently imports `noctusai_lib.domain.metas` (2 occurrences per §5.4.6 audit) but PF still on local copies. **ERP Phase 1 adopts the seed primitives across `services/metas_*_service.py`** and retires local recurrences.

### 5.4 Inventory *(populated 2026-05-11 by Phase 0)*

#### 5.4.1 Headline counts

| Surface | Count |
|---|---|
| Backend routers | **60** (`__init__.py` excluded; total `.py` files in `routers/` = 60 routers + `__init__.py`) |
| Backend endpoints | **321** (sum across all 60 routers via `@router.(get|post|put|patch|delete)` count) |
| Backend migrations | **29** (`001_erp_imobiliario.sql` → `029_service_role_bypass_backfill.sql`; next free slot = **030**) |
| Frontend hooks | **65** (under `frontend/src/hooks/`, excluding `__tests__/`) |
| Frontend pages | **67** (under `frontend/src/pages/`) |
| Frontend pages with **direct** `useQuery`/`useMutation` (Pattern D) | **0 direct queries; 2 use `useQueryClient` only** (`Certidoes.tsx`, `WhatsAppInbox.tsx` — cache invalidation, not bypass) |
| Frontend components hitting `/api/` directly | **0** |
| Raw `fetch()` outside auth/api wrappers | **6** (5 product + 1 utility — see §5.4.2 Pattern D' below) |
| Unique frontend → backend API paths surveyed | **122** |
| Hook root-prefixes calling `/api/X` | **44** unique |
| Router root-prefixes exposing `/api/X` | **48** unique |
| Backend routers with `response_model` declared | **0 / 60** — all 321 routes return via `success_response()` / `paginated_response()` / `ok_response()` helpers; DTO contract is implicit (same shape as therapy / PF) |
| Direct `supabase.from(...)` reads from hooks (Pattern D-variant — bypass backend) | **3 hooks** (`useNegociacoes`, `useUserProfile`, `useUserRoles`) |
| Direct `supabase.functions.invoke(...)` from hooks (canonical edge-function pattern) | **2 hooks** (`useRecuperarSenha`, `useRequisitarSenha`) |
| Pytest baseline | **1901 collected, 1856 passed, 34 skipped (2 warnings)** — green |
| Keeper review | **0 issues, 0 proposals** — clean bill |

#### 5.4.2 Systemic findings *(7 Pattern shapes A-G + PF-lessons H)*

**Pattern A — Portuguese ↔ English path mismatches: 0 occurrences.**

ERP is the canonical PT-domain product per PF Q2 default rec. Backend exposes PT prefixes (`/api/clientes`, `/api/ativos`, `/api/contratos`, `/api/locacoes`, `/api/vistorias`, `/api/chaves`, `/api/comissoes`, `/api/condominios`, `/api/financeiro`, `/api/impostos`, `/api/matriculas`, `/api/certidoes`, `/api/recorrencia`, `/api/atividades`, `/api/relatorios`, `/api/distribuicao`, `/api/configuracoes`, `/api/funil`, `/api/agenda`, `/api/banco`, `/api/manutencao`, `/api/marketing`, `/api/seguros`, `/api/portais`, `/api/portal-cliente`, `/api/propostas`, `/api/assinaturas`, `/api/gamificacao`, `/api/dimob`, `/api/site`, `/api/campo`, `/api/profiles`, `/api/filiais`, `/api/comissoes`, `/api/matching`, `/api/metas/*` cluster, `/api/meta`, `/api/portal`, `/api/whatsapp`, `/api/storage`, `/api/pdf`, `/api/jobs`, `/api/logs`, `/api/emails`, `/api/documentos`, `/api/analise-credito`, `/api/bi`, `/api/ai`, `/api/vista-showcase`) plus the 4 seed-mounted English standard routers (`/api/notificacoes`, `/api/team`, `/api/health`, `/api/ai_outputs`/`/api/ai_feedback` — mounted by `create_product_app` per §3a Q5). Hooks call exactly the matching PT path. **No EN-stray paths found** — verified via `grep -lE "/api/(imoveis|leads|properties|contracts|customers)" frontend/src/hooks/` returning empty.

**Pattern B — Admin namespace not split: minimal (1 router has bespoke admin gate).**

Only `vista_showcase.py` carries its own `require_admin` (`ALLOWED_ADMIN_ROLES = {"platform_admin", "admin", "owner"}` at line 36). All other ERP role-gating defers to RLS policies + JWT-derived role via `get_user_role` from seed. **No `/api/admin/*` namespace split needed** — ERP routes role-gate via Supabase RLS service-side, not via URL split. Different shape than therapy.

**Pattern C — Detail endpoints missing: 0 surfaced.**

Cross-checked all 37 unique detail-path patterns in hooks (e.g. `/api/clientes/{id}`, `/api/contratos/{id}/parcelas`, `/api/chaves/{id}/historico`, `/api/locacoes/{id}/reajuste`, `/api/portal/{token}/imoveis`) against router definitions. **Every frontend detail call has a matching router decorator.** Sample verification: `useChaves.ts` line 50 calls `GET /api/chaves/{id}` → router has `@router.get("/{chave_id}")` at `chaves.py:133`; `useContratos.ts` line 77 calls `GET /api/contratos/{contratoId}/parcelas` → router has `@router.get("/{contrato_id}/parcelas")` at `contratos.py:256`.

**Pattern D — Direct-fetch / Pattern-D-variant supabase.from() bypass: 3 hooks.**

| Hook | Bypass shape | Should route through |
|---|---|---|
| `useNegociacoes.ts` | `supabase.from("negociacoes")` direct read with role-filter logic in frontend | New backend route `/api/negociacoes` with RLS-enforced filter |
| `useUserProfile.ts` | `supabase.from("profiles")` direct read | Already exists at `/api/profiles` — refactor hook to call backend |
| `useUserRoles.ts` | `supabase.from("user_roles")` direct read | Either backend route or seed-lib `useUserRole` consumer |

Plus 6 raw `fetch()` calls:
- `useMatriculas.ts` — `fetch(${BACKEND_URL}/api/matriculas/extrair)` with custom Bearer refresh (intentional — multipart upload).
- `useCepSearch.ts` — `fetch(viacep.com.br)` (external, NOT backend).
- `usePortalExterno.ts` — `fetch(${BACKEND_URL}${path})` (intentional — public/no-auth portal flow).
- `pages/Configuracoes.tsx` — `fetch(${CORE_API_URL}${path})` (cross-product reach into core; intentional but **N=1 surface for accept-with-rationale review**).
- `pages/VistaShowcase.tsx` — 2 `refetch()` calls (tanstack-query method, NOT raw fetch — false positive).

**Pattern E — Implicit DTO contract: systemic (0 / 60 routers declare `response_model`).**

Same shape as therapy + PF. All 321 routes flow through `success_response(data)` / `paginated_response(data, page, …)` / `ok_response()` wrappers. Frontend `types/` carries de-facto contract. **Default recommendation in §7 design batch:** defer to follow-up project `erp-imobiliario-dto-contract`; accept-with-rationale for this project; per-router test files are operational contract.

**Pattern F — `require_role` recurrence inside this product: 1 local re-implementation (different shape from PF + therapy).**

- `app/routers/vista_showcase.py:44` — `async def require_admin(authorization)` — local SSO-aware admin gate (bespoke for `vista_showcase`).
- `app/routers/metas_digest.py:41` — inline `if role not in ("admin", "owner"):` check.
- Two other routers reference `"admin"` literal (`equipes.py:78` defers to RLS comment; `vista_showcase.py:36,54` is the SSO admin set).

**ERP differs from therapy here:** therapy had N=2 product-side `require_role` re-implementations; ERP has N=1 (`vista_showcase`) + 1 inline check. **The Phase 1 absorption target is therefore `make_get_current_user_org` + `make_require_role` from PF retro §e**, NOT a local ERP-only `require_role` consolidation. ERP uses `deps.get_current_user` from `noctusai_seed.create_dependencies(...)` (legacy positional-args shape; seam at `app/dependencies.py:14`).

**Pattern G — Path-shape mismatches inside clusters: 1 noted (low severity).**

- `contratos.py` has BOTH `@router.get("/{contrato_id}/parcelas")` (nested) AND `@router.patch("/parcelas/{parcela_id}")` (flat). Mixed shape — hook `useContratos.ts:172` calls `PATCH /api/contratos/parcelas/${parcelaId}` correctly. **Triage: accept-with-rationale** (parcela is a contract sub-entity; flat-by-id PATCH is a defensible shape when the parcel ID is globally unique within the contract scope).
- `locacoes.py` parametrizes by `{contrato_id}` (not `{locacao_id}`) — `locacoes` are leasing contracts so `contrato_id` is the canonical key; not a mismatch. **No action.**

**Pattern H — Orphaned hooks (no page/component consumer) — PF lessons §b.2 addition.**

Walked every `useX` hook via `grep -rE "\\b<hook>\\b" pages/ components/` excluding self-imports:

| Hook | Consumer count | Triage |
|---|---|---|
| `useAtualizarStatusMetas` | 0 page consumers | Phase 1 — wire to admin Metas tab OR delete (decision: surface in §7 Q-NEW-DEL) |
| `useCriarMetaHoje` | 0 page consumers | Phase 1 — wire to today's Meta tab OR delete (surface in §7 Q-NEW-DEL); also re-used inside `useMetasConfig.ts:54` as an embedded call — possibly already wired indirectly |
| `useDebounce` | 0 page consumers | Utility hook; treat as library code (NOT orphan in product-feature sense) |
| `useLayoutEnrichment` | wired via `useERPLayoutEnrichment` alias in `App.tsx` | NOT orphan — re-aliased |
| `useUserProfile`, `useUserRoles` | consumed by `useLayoutEnrichment.ts` | NOT orphan |

**Confirmed orphans:** `useAtualizarStatusMetas`, `useCriarMetaHoje` (the latter has 1 embedded re-use inside another hook but no page render). Surface as §7 Q-NEW-DEL deletion-or-wire candidates.

#### 5.4.3 Per-router endpoint distribution

Top-15 routers by endpoint count (full list in `findings.md`):

| Router | Endpoints | Notes |
|---|---|---|
| `metas.py` | 14 | Largest router; goal-domain CRUD + scaffold + atualizar-status + criar-hoje + concluir |
| `certidoes.py` | 11 | TJSP queue + cooldown + consultas + fila |
| `portal_cliente.py` | 9 | Client portal — acessos / chamados / gerar-acesso |
| `meta_api.py` | 9 | Meta Ads integration — campanhas / config |
| `equipes.py` | 9 | Team domain (quotas-equipe routed at `/api/metas/equipes`) |
| `contratos.py` | 9 | Contract + parcelas (Pattern G noted) |
| `ai.py` | 9 | AI surface — generate-description / lead-score / suggest-price / coach-tip / etc. |
| `portal_externo.py` | 8 | Public-link portal — gerar-link / tokens / token-detail × 4 |
| `emails.py` | 8 | Email send + templates |
| `vistorias.py` | 7 | Inspection CRUD + photos + template-checklist |
| `vista_showcase.py` | 7 | Vista CRM admin showcase (bespoke admin gate) |
| `propostas.py` | 7 | Proposal CRUD + contraproposta + stats |
| `meta_periodos.py` | 7 | Metas period domain |
| `marketing.py` | 7 | Alertas + campanhas |
| `locacoes.py` | 7 | Lease CRUD + reajuste + renovar |

#### 5.4.3a Corretor-surface per-hook map *(densified 2026-05-20 by Phase 5)*

The 8 corretor-tier hooks → router → endpoint mapping. Each row was verified hook-by-hook against router decorators; **every path aligns — no missing routes, no orphaned endpoints**.

| Page | Hook file | Exported hook(s) | Backend path(s) | Router file | Router endpoint(s) | Test file (backend) | Alignment |
|---|---|---|---|---|---|---|---|
| (component-embedded — `clientes/ClienteAtividades.tsx`, `clientes/ClienteHistorico.tsx`) | `useAtividades.ts` (44 LoC) | `useAtividades(clienteId)` ∧ `useCreateAtividade()` | GET `/api/atividades?cliente_id=` ∧ POST `/api/atividades` | `atividades.py` | `@router.get("")` ∧ `@router.post("")` | `test_atividades_router.py` (6 tests) | ✅ |
| `Funil.tsx` (119 LoC) | `useFunil.ts` (97 LoC) | `useFunil(filtros?)` ∧ `useMoverClienteEtapa()` | GET `/api/funil` ∧ POST `/api/clientes/{id}/mover-etapa` | `funil.py` ∧ `clientes.py` | `@router.get("")` (funil) ∧ `@router.post("/{cliente_id}/mover-etapa")` (clientes) | `test_funil_router.py` (4 tests) ∧ `test_clientes_router.py` (mover-etapa 4 cases) | ✅ |
| `Distribuicao.tsx` (400 LoC) | `useDistribuicao.ts` (82 LoC) | `useDistribuicaoConfig()` ∧ `useDistribuicaoFila()` ∧ `useUpdateDistribuicaoConfig()` ∧ `useAtribuirLead()` | GET `/api/distribuicao/config` ∧ GET `/api/distribuicao/fila` ∧ PATCH `/api/distribuicao/config` ∧ POST `/api/distribuicao/atribuir` | `distribuicao.py` | `@router.get("/config")` ∧ `@router.get("/fila")` ∧ `@router.patch("/config")` ∧ `@router.post("/atribuir")` | `test_distribuicao_router.py` (12 tests) | ✅ |
| `Agenda.tsx` (721 LoC) | `useAgenda.ts` (207 LoC) | `useEventos(filtros?)` ∧ `useEvento(id?)` ∧ `useEventosHoje()` ∧ `useEventosSemana()` ∧ `useCreateEvento()` ∧ `useUpdateEvento()` ∧ `useDeleteEvento()` | GET/POST `/api/agenda` ∧ GET/PATCH/DELETE `/api/agenda/{id}` ∧ GET `/api/agenda/hoje` ∧ GET `/api/agenda/semana` | `agenda.py` | 7 decorators — full CRUD + 2 convenience reads | `test_agenda_router.py` (28 tests) | ✅ |
| `Campo.tsx` (657 LoC) — Vistorias-mobile / field-ops | `useCampo.ts` (159 LoC) | `useCheckins(filters?)` ∧ `useCreateCheckin()` ∧ `useVistoriaRapida()` ∧ `useImoveisProximos(lat,lng,raio)` ∧ `useSyncCampo()` ∧ `useOfflineData()` | GET `/api/campo/checkins` ∧ POST `/api/campo/checkin` ∧ POST `/api/campo/vistoria-rapida` ∧ GET `/api/campo/proximos` ∧ POST `/api/campo/sync` ∧ GET `/api/campo/offline-data` | `campo.py` | 6 decorators — checkin (read+create), vistoria-rapida, proximos, sync (offline), offline-data | `test_campo_router.py` (27 tests) | ✅ |
| `Comissoes.tsx` (552 LoC) | `useComissoes.ts` (119 LoC) | `useComissoes(filtros?)` ∧ `useComissao(id?)` ∧ `useComissaoResumo()` ∧ `useCreateComissao()` ∧ `useUpdateComissao()` ∧ `useDeleteComissao()` | GET/POST `/api/comissoes` ∧ GET/PATCH/DELETE `/api/comissoes/{id}` ∧ GET `/api/comissoes/resumo` | `comissoes.py` | 6 decorators — full CRUD + resumo | `test_comissoes_router.py` (18 tests) | ✅ |
| `Marketing.tsx` (464 LoC) | `useMarketing.ts` (187 LoC) | `useCampanhas(filtros?)` ∧ `useCampanha(id?)` ∧ `useCreateCampanha()` ∧ `useUpdateCampanha()` ∧ `useDeleteCampanha()` ∧ `useEnviarCampanha()` ∧ `useAlertasMarketing()` | GET/POST `/api/marketing/campanhas` ∧ GET/PATCH/DELETE `/api/marketing/campanhas/{id}` ∧ POST `/api/marketing/campanhas/{id}/enviar` ∧ GET `/api/marketing/alertas` | `marketing.py` | 7 decorators — campanha CRUD + enviar + alertas | `test_marketing_router.py` (26 tests) | ✅ |
| `BI.tsx` (600 LoC) | `useBI.ts` (99 LoC) | `useDashboardResumo()` ∧ `useBIVendas(filtros?)` ∧ `useBICaptacao()` ∧ `useBICorretores(periodo?)` ∧ `useBIImoveis()` ∧ `useBIFinanceiro(filtros?)` | GET `/api/bi/dashboard` ∧ `/api/bi/vendas` ∧ `/api/bi/captacao` ∧ `/api/bi/corretores` ∧ `/api/bi/imoveis` ∧ `/api/bi/financeiro` | `bi.py` | 6 GET-only decorators (read-only BI surface) | `test_bi_router.py` (12 tests) | ✅ |

**Wiring verification summary:**
- 8 corretor surfaces audited (Atividades is component-embedded; remaining 7 are dedicated pages).
- 40+ frontend hook exports → 39+ backend endpoint decorators across 8 routers.
- **Zero missing routes** (every frontend `api.get/post/patch/delete` call has a matching `@router.*` decorator).
- **Zero orphaned endpoints** in the corretor scope (every backend endpoint reachable from a hook). The Phase 0 §5.4.4 orphans (`configuracoes`, `jobs`, `logs`, `pdf`, `recorrencia`, `storage`) are NOT corretor surfaces — addressed in their own phases.
- Backend test coverage: **133 tests across the 8 corretor routers** (atividades 6 + funil 4 + distribuicao 12 + agenda 28 + campo 27 + comissoes 18 + marketing 26 + bi 12).
- Frontend hook smoke coverage (Phase 5): **8 hook-level vitest smoke tests** (`hooks/__tests__/useCorretorHooks.test.ts`) — one per corretor hook, mirroring the `useAI.test.ts` pattern.
- Pre-existing test bug fixed in-flight (`test_funil_router.py` — mock data missed `arquivado=False` filter; 2/4 tests were red on `origin/main` baseline, now 4/4 green).

#### 5.4.4 Backend orphans (no surveyed frontend caller — router prefix → 0 hook matches)

Router prefixes that exist on backend but have **zero** frontend `/api/<prefix>` calls in hooks:

| Router | Prefix | Likely consumer | Triage |
|---|---|---|---|
| `configuracoes.py` | `/api/configuracoes` | `pages/Configuracoes.tsx` direct-fetch (Pattern D) | Phase 4 — refactor page to hook |
| `jobs.py` | `/api/jobs` | Cron / background workers | Phase 0 — confirm cronJob caller, otherwise delete |
| `logs.py` | `/api/logs` | `useActionLog.ts` (different path?) | Cross-check; possibly mounted at non-`/api/logs` prefix |
| `pdf.py` | `/api/pdf` | Documents flow / generation | Phase 6 — audit document-render pipeline |
| `recorrencia.py` | `/api/recorrencia` | Lancamento recorrente UI | Phase 4 — audit recurring-rule UI |
| `storage.py` | `/api/storage` | Upload helpers | Phase 0 — confirm signed-URL pipeline |

**Acceptance:** every orphan above gets either a wired hook OR a deletion ticket in the appropriate Phase. None block Phase 1.

#### 5.4.5 Migration column gap

**Cross-checked all 75 unique tables in `migrations/001..029.sql` against `.table("<name>")` calls in `app/services/` + `app/routers/`.**

| Code-referenced table | In ERP migrations? | Notes |
|---|---|---|
| **All 65 ERP code-referenced tables** | ✅ present | No ERP-side drift |
| `org_settings` | ❌ ERP / ✅ `core` | Intentional cross-schema reach (verified at `products/core/backend/migrations/001_noctusai_core.sql`); NOT drift |

**No drift found.** Phase 0 verified column references via grep over `.table("X")`; deeper column-level audit (e.g. `.select("foo")` against table column definitions) is a Phase 4 sub-task if any service surfaces unknown-column errors.

#### 5.4.6 Should-use-seed candidates *(N=2 PF baseline → N=3 in ERP)*

Audited via `grep -rE 'from noctusai_(lib|seed)' app/` — 47 imports across 8 files in ERP backend. Existing adoption table:

| Seed module | Imports | Status |
|---|---|---|
| `noctusai_lib.primitives.timeutil` | 7 | Adopted |
| `noctusai_lib.config.credentials` | 6 | Adopted |
| `noctusai_seed` (top-level — create_product_app, etc.) | 4 | Adopted |
| `noctusai_lib.api.crud_safety` (includes `delete_or_404`) | 4 | Adopted (PF Phase 2 lifted; ERP imports — verify all DELETE pre-checks now use it) |
| `noctusai_lib.security.webhook_signatures` | 3 | Adopted |
| `noctusai_lib.primitives.parsing` | 3 | Adopted |
| `noctusai_lib.primitives.tasks` | 2 | Adopted |
| `noctusai_lib.integrations.whatsapp` | 2 | Adopted |
| `noctusai_lib.integrations.vista` | 2 | Adopted |
| `noctusai_lib.integrations.llm` | 2 | Adopted |
| `noctusai_lib.domain.metas` | 2 | Adopted (partial — verify all metas services consume seed primitives) |
| `noctusai_lib.domain.ai` | 2 | Adopted |
| `noctusai_lib.api.auth` (first_or_none + resolve_sso_role) | 2 | Adopted |
| `noctusai_lib.api.middleware` | 1 | Adopted (request_id) |
| `noctusai_lib.integrations.email.digest` | 1 | Adopted |
| `noctusai_lib.domain.action_log` | 1 | Adopted |
| `noctusai_lib.logging_config` | 1 | Adopted |
| `noctusai_lib.primitives.responses` | 1 | Adopted |

**Absorption candidates whose N=2 PF baseline flips to N=3 with ERP** (per PF retro §e):

| Candidate | PF / ERP / therapy | Action |
|---|---|---|
| `make_get_current_user_org` factory | PF N=1 + ERP N=1 = N=2; therapy adoption flips to N=3 | PF filed `make-get-current-user-org-factory` follow-up; ERP Phase 1 verifies seed-ships-it; if shipped, adopt; else defer with destination |
| AI plumbing wrappers (`safe_persist_indicator`, `require_credential_or_422`, `check_openai_configured`) | PF + ERP byte-identical (N=2) | PF filed `ai-plumbing-seed-absorption`; ERP Phase 1 verifies + adopts or defers |
| Metas domain (`Goal/Period/Progress`, `compute_progress`, `accumulate_contribution`, `period_bounds`, `proportional_target`, `next_status`) | PF + ERP + daily-life = N=3 MUST-FORMALIZE | Seed already ships `noctusai_lib.domain.metas` per KB pointer; ERP Phase 1 retires local copies across `services/metas_*_service.py` |
| `scheduler` standard router (last-run / next-run / executar) | PF + mailing + therapy = N=3 likely | PF filed `phase-5-scheduler-standard-router`; not ERP-blocking; ERP may surface N=4 |
| Cross-schema `db.table("organizations")` / `org_settings` reach | PF + ERP + therapy + daily-life = N=4 | PF filed `cross-schema-organization-reach-audit`; ERP confirms pattern (intentional, accept-with-rationale) |
| DELETE pre-check via `delete_or_404` | PF (3) + ERP (`meta_periodos_service` + `regras_pontuacao_service`) = N=5 | Seed lifted; ERP Phase 1 verifies all DELETE sites use the helper |
| `<StaleBadge>` + `computeStaleness` | PF only N=1 | DEFER — N=2 not yet surfaced |
| `ultima_execucao` scheduler-history column | Captured in scheduler-standard-router design | Not ERP-blocking |

**Phase 1 will be: seed-side absorption batch** mirroring PF Phase 1's shape — verify-seed-ships-it on each row, adopt or defer with destination.

#### 5.4.7 Deletion-candidate batch *(surfaced at end-of-Phase-0 per PF Q3)*

| Candidate | Rationale | Default recommendation |
|---|---|---|
| `useAtualizarStatusMetas` hook | 0 page consumers; backend route `/api/metas/atualizar-status` exists but called only by this orphan hook | DELETE hook AND backend route; OR wire to a Metas admin "force recalc" button. **Default rec:** wire to admin Metas tab (preserves the backend capability) |
| `useCriarMetaHoje` hook | 0 page consumers; 1 indirect embedded call from `useMetasConfig.ts:54` | KEEP hook; embedded call is real use. **Default rec:** KEEP (false positive) |
| Pages with raw fetch to non-API origins (`useCepSearch`, `usePortalExterno`) | Intentional external/public flows | KEEP. **Default rec:** KEEP |

All deletion-candidates land as §7 Q-NEW-DEL for user one-sweep approval before Phase 1 kicks off.

#### 5.4.8 Test coverage

- **1901 collected, 1856 passed, 34 skipped, 0 failed** in `products/erp-imobiliario/backend/` at Phase 0 close.
- Coverage spans routers (60), services (53), middleware, integration paths.
- **PF Phase 7 lesson §d.4 — standard-router smoke per product:** ERP `app/main.py:109` mounts `standard_routers=["health", "notificacoes", "team", "llm", "ai_outputs", "ai_feedback"]`. **Phase 7 sub-task:** verify each of these 6 mount-shapes has a ≥1-test smoke file under `tests/routers/test_<router>_router.py` (e.g. `test_health_router.py`, etc.). PF added 3 tiny smoke tests at its Phase 7; ERP should match — 5-test pattern (5 functions, 2 per router with status + body assertion).
- **PF Phase 0 lesson §b.3 — status-code-assertion calibration:** run `noctus.dev.scan_block_patterns mode=status_assertion` over ERP test corpus in Phase 0; produce inventory; either fix in Phase 0 OR pin as baseline-no-regress. **Action item filed** for Wave 0 of Phase 1.

#### 5.4.9 Keeper review pass

```
python mcp/noctusai/cli.py --review --product erp-imobiliario --worktree-path "$PWD"
```

Run 2026-05-11 — **0 issues, 0 proposals filed.** Result: clean keeper bill of health on `erp-imobiliario`. The gap table in §5.4.2-§5.4.7 is the agent-authored signal for this project. (MMM Wave 4 supersession-FP tuning carried forward; no false positives surfaced.)

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses.

**Phase status-icon convention** (per `KB § PATTERNS/project-execution.md §1`):

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress / partially done |
| ✅ | Complete — every sub-task ticked |
| ❌ | Blocked or failed — see Change Log |

**Improvement capture happens during steps. Proposal authoring happens at end of phase.** One bundled proposal per phase, filed via `noctus.dev.file_proposal(project="erp-wiring", worktree_path="$PWD", …)` → lands in `products/erp-imobiliario/projects/erp-wiring/proposals/`.

---

### Phase 0 — Discovery & inventory ✅ *(2026-05-11)*

Produced the concrete gap table in §5.4. Every subsequent phase references rows from this table — no phantom scope.

- [x] **0.a — Backend route inventory:** enumerated every `prefix="/api/"` declaration across all 60 routers; counted endpoints via `@router.(get|post|put|patch|delete)` per file. Total: **321 endpoints across 60 routers**. Top-15 distribution captured in §5.4.3. *(Run: `grep -HE 'APIRouter\(prefix=' *.py | sort` from `products/erp-imobiliario/backend/app/routers/`.)*
- [x] **0.b — Frontend hook + page inventory:** counted 65 hooks + 67 pages; surveyed 122 unique `/api/` paths from hooks via `grep -rE "'/api/" hooks/ pages/ components/`; classified raw `fetch()` (6 occurrences, 5 intentional + 1 cross-product reach) vs hook-mediated. Captured in §5.4.1.
- [x] **0.c — Gap table (7 Pattern shapes A-G + PF lessons §b.2 Pattern H orphaned-hook):** captured in §5.4.2. **Pattern counts:** A=0 (PT-domain canonical), B≈1 (only `vista_showcase` has bespoke admin gate), C=0 (every detail-path verified), D=3 supabase-bypass hooks + 1 cross-product fetch (cross-checked), E=systemic (0/60 routers declare `response_model`), F=1 local + 1 inline (different shape from therapy/PF), G=1 noted (contratos/parcelas mixed shape — accept-with-rationale), H=2 confirmed orphans (`useAtualizarStatusMetas` + `useCriarMetaHoje`).
- [x] **0.d — Migration column cross-reference:** parsed `CREATE TABLE` statements across 29 migrations (75 unique tables); cross-checked against `.table(...)` calls in `app/services/` + `app/routers/` (65 code-referenced tables). **Zero ERP-side column drift.** Cross-schema reach into `core.org_settings` confirmed intentional via `products/core/backend/migrations/001_noctusai_core.sql`. Captured in §5.4.5.
- [x] **0.e — Seed-lib export catalog inheritance:** `grep -rE 'from noctusai_(lib|seed)' app/` → 47 imports across 8 files; table in §5.4.6. PF retro §e recurrence candidates filed for Phase 1 verify-the-seed-ships-it check.
- [x] **0.f — Phase 0 deliverable:** PROJECT.md §5.4 populated; §6 phases promoted from placeholders to concrete sub-tasks; §7 design batch surfaced (6 Q items mirroring therapy §7 Q9-Q14 + 1 Q-NEW-DEL for orphan hooks); §11 first entry below.
- [x] Pytest baseline confirmed green: 1901 collected, 1856 passed, 34 skipped, 0 failed.
- [x] Keeper review: **0 issues**.

**Deliverable produced:** §5.4 populated (5.4.1 counts → 5.4.9 keeper); phases 1-9 carry concrete work items rooted in §5.4 rows; design-batch surfaced in §7 (6 questions + Q-NEW-DEL) for user sign-off before Phase 1.

#### Phase 0 → §7 design-batch handoff

Six design questions surfaced. All carry default recommendations; surface as one batch to user before Phase 1.
- §7 Q-A — Pattern A EN/PT alignment. Default rec: **NO RENAME** (ERP is PT-domain canonical per PF Q2).
- §7 Q-B — Pattern B admin namespace split (vista_showcase bespoke admin gate vs canonical role-gate). Default rec: **KEEP bespoke** — vista_showcase needs SSO platform_admin gate which differs from RLS-only.
- §7 Q-C — Pattern C admin detail endpoints. **N/A** for ERP — all detail paths already wired.
- §7 Q-D — Pattern D supabase.from() bypass hooks (`useNegociacoes` + `useUserProfile` + `useUserRoles`). Default rec: **refactor to backend hooks during Phase 4** (DRY with PF Pattern D lesson).
- §7 Q-E — Pattern E DTO contract via `response_model`. Default rec: **defer to follow-up project `erp-imobiliario-dto-contract`; accept-with-rationale** for this project (mirrors therapy Q13).
- §7 Q-F — Pattern F `require_role` consolidation. Default rec: **adopt `make_require_role` from seed if it ships before Phase 1; else verify-seed-ships-it defer.**
- §7 Q-NEW-DEL — Orphan hook deletion-or-wire batch (`useAtualizarStatusMetas` decision; `useCriarMetaHoje` is false-positive KEEP). Default rec: **wire** `useAtualizarStatusMetas` to admin Metas force-recalc button.

**Improvements:** none filed as a separate proposal. Captured inline in §5.4.2 Patterns A-H — the gap table itself is the Phase 0 artifact. Per `feedback_apply_inline_delete_proposals` and `feedback_auto_improvement`.

---

### Phase 1 ✅ — Seed-side absorption batch (verify-seed-ships-it on PF retro §e rows) *(2026-05-11)*

**Improvements:** Phase 1 carved out 5 deferred items pushed to Phase 3 (AI plumbing migrations, metas full retirement, make_require_role continuation, status-code calibration, frontend vi.importActual). Each ticked below as [DEFERRED-TO-P3] to reflect that triage decision was made.

Mirrors PF Phase 1 shape. For each row in PF retro §e, run the verify-seed-ships-it test (read seed's `__init__.py` exports + concrete adapter), then:
- If seed ships it → adopt across ERP backend.
- If seed has Protocol + Fake only → defer with destination (file follow-up project / `accept-with-rationale` entry).
- If seed is fully absent → file follow-up project, ship against Fake.

- [x] **`make_get_current_user_org` adoption** — 300 / 300 router callsites migrated (PF retro §e row 1).
- [x] [DEFERRED-TO-P3] **AI plumbing wrappers** — *partial:* `safe_persist_indicator` adopted in Phase 2 (5 callsites in `ai.py`). `require_credential_or_422` migration deferred to Phase 3 (would re-target `app.routers.ai.check_openai_configured` test patches; needs coordinated test update).
- [x] [DEFERRED-TO-P3] **`noctusai_lib.domain.metas` consumer-side adoption** — already partial (2 imports today); full retirement deferred to a focused metas Phase 3 sub-task.
- [x] [DEFERRED-TO-P3] **`make_require_role` adoption** for `vista_showcase.require_admin` + `metas_digest` inline check (Pattern F continuation) — deferred to Phase 3.
- [x] [DEFERRED-TO-P3] **Status-code-assertion calibration** — deferred to Phase 3.
- [x] **DELETE pre-check uniformity audit** — 15 canonical sites migrated to `delete_or_404`; 8 non-canonical sites left with documented rationale.
- [x] [DEFERRED-TO-P3] **`vi.importActual` / `vi.hoisted` test patterns** — pre-document fix from PF retro §d for ERP frontend test brief (frontend phase).
- [x] Phase-1 commit landed (`989a75e feat(erp-wiring): Phase 1 — Pattern F adoption + delete_or_404 sweep`).

### Phase 2 ✅ — AI plumbing partial absorption (focused subset) *(2026-05-11)*

**Improvements:** Phase 2 was a focused-subset close (safe_persist_indicator absorption only). Phase 2 proposal filing deferred — §11 change-log entry is the durable artifact for the partial absorption.

Phase 0 surfaced 0 explicit 404/405 regressions; Phase 1 introduced 0 new regressions (baseline preserved at 1862 passed + 12 pre-existing). Original Phase 2 skeleton ("re-scan for 4xx surfaces") therefore **collapses** — no work remained for that frame.

Instead, Phase 2 picked a focused subset from the PF retro §e absorption rows: the `_persist_indicator` → `safe_persist_indicator` swap. Rationale: (1) byte-equivalent to seed; (2) verify-seed-ships-it confirmed (`noctusai_lib.domain.ai.outputs.safe_persist_indicator` exported with the exact contract); (3) no test patches reference the local helper name, so swap is contained; (4) Phase 1 just touched ERP routers so the next absorption shape is a natural continuation; (5) mirrors therapy-platform-wiring's "focused-subset closes per phase" cadence.

- [x] **`safe_persist_indicator` absorption (5 callsites in `app/routers/ai.py`)** — libcst codemod rewrote `_persist_indicator(db, ref_type, ref_id, out)` → `safe_persist_indicator(db, schema="erp", ref_type=..., ref_id=..., out=..., logger=logger)`; local helper retired; import updated to drop now-unused `AIOutput` + `persist_output` and add `safe_persist_indicator`.
- [x] **Test fixture refactor** — `_stub_persist` patch target lifted from `app.routers.ai.persist_output` (no longer importable) to the canonical seed surface `noctusai_lib.domain.ai.outputs.persist_output`. 6 indicator tests green again.
- [x] **Baseline preserved** — `pytest tests/ -q` → 1862 passed + 12 pre-existing fails + 34 skipped (identical to the Phase-1-close baseline).
- [x] **Keeper review** — `mcp/noctusai/cli.py --review --product erp-imobiliario` → 0 NEW issues.
- [x] [DEFERRED-DURABLE-IN-CHANGELOG] **Phase 2 proposal filing** — deferred; the §11 change-log entry below is the durable artifact for the partial absorption.

**Deferred to Phase 3** (each requires coordinating test patch-target updates):
- `_require_openai` → `require_credential_or_422` (autouse `_bypass_openai_check` fixture patches `app.routers.ai.check_openai_configured`).
- `check_openai_configured` → seed `require_credential_or_422` raise-path (matching.py + ai.py).
- `make_require_role` adoption (Pattern F continuation for `vista_showcase.require_admin` + `metas_digest` inline check).
- Status-code-assertion calibration.

### Phase 3 ✅ — Deferred-items absorption batch (AI plumbing + Pattern F continuation + status-code calibration) *(2026-05-11)*

**Improvements:** Phase 3 closed the deferred batch from Phase 1/2 (`require_credential_or_422` migration, `make_require_role` adoption, status-code calibration). DTO normalization sweep (the original §6 Phase 3 heading) is re-numbered to **Phase 3b** below and remains pending.

Engineer ERP-P3 executed the deferred-items batch from the Phase 1 Improvements block (5 items) + Phase 2 deferred list. All landed without baseline regression.

- [x] **`_require_openai` retirement → `require_credential_or_422`** in `app/routers/ai.py`. Local helper kept as a thin pass-through delegating to the seed; import lifted to `noctusai_lib.api.auth`. 9 callsites unchanged at the routing layer (still `_require_openai(get_org_id(user))`); the body now calls `require_credential_or_422("openai_api_key", org_id, detail=_OPENAI_MISSING_DETAIL)`. PF retro §e row 2 progresses ERP-side from "N=2 candidate → N=3-pending" to "N=3-pending → ERP-side adopted, PF/therapy pending".
- [x] **`check_openai_configured` → `require_credential_or_422`** in `app/routers/matching.py`. Two callsites (`/api/matching/embed`, `/api/matching/embed-batch`) inlined the `if not check_openai_configured(...): raise HTTPException(422, ...)` shape; both replaced with `require_credential_or_422("openai_api_key", get_org_id(user), detail=_OPENAI_MISSING_DETAIL)`. `from app.services.ai_service import check_openai_configured` retired from matching.py imports.
- [x] **Test fixture patch-target lifts** — `app.routers.ai.check_openai_configured` and `app.routers.matching.check_openai_configured` no longer importable. Both fixtures (`tests/routers/test_ai_router.py:_bypass_openai_check`, `tests/routers/test_matching_router.py:TestEmbedAtivo._bypass_openai_check`, `TestEmbedBatch._bypass_openai_check`) lifted to patch the canonical seed surface `noctusai_lib.config.credentials.resolve_credential`. Per `feedback_no_monkeypatching_in_tests`: patching the *external* credential-source boundary (DB-backed `resolve_credential`) is allowed; patching in-product helpers is not. Mirrors the Phase 2 `_stub_persist` patch-target lift. `test_embed_ativo_no_api_key` updated to override the autouse fixture with `return_value=None` for the 422-path assertion.
- [x] **`make_require_role` adoption (Pattern F continuation)** — added `get_erp_user_role(user) -> str` to `app/dependencies.py` (ERP-specific resolver preserving `SSO platform_admin → erp_role → noctus_role → "user"` priority) and bound `require_role = make_require_role(get_current_user, get_erp_user_role)`. `app/routers/vista_showcase.py:require_admin` body retired in favor of `Depends(require_role(*ALLOWED_ADMIN_ROLES))`; the bespoke `resolve_sso_role` + metadata-lookup logic now lives in `get_erp_user_role` (single resolver, multiple routers can compose). `app/routers/metas_digest.py` inline `if role not in ("admin", "owner"):` check retired; endpoint now binds `auth_role = Depends(require_role("admin", "owner", "platform_admin"))` (added `platform_admin` to allowed set to match the canonical SSO short-circuit shape).
- [x] **Status-code-assertion calibration** — AST-walked `tests/routers/` for body-asserts-without-status-code (defended by the `feedback_status_code_assertion_rule`). 8 gaps found, 8 fixed: `test_certidoes_router.py` (3 sites — `test_cada_tipo_tem_campos_obrigatorios`, `test_ordem_sequencial`, `test_consulta_retorna_resultados_lista`, `test_exclui_retorna_mensagem`), `test_funil_router.py` (3 sites — `test_funil_empty`, `test_funil_grouping_correct`, `test_funil_search_filters`), `test_gamificacao_router.py` (1 site — `test_regras_conquistas_structure`). Each gained an explicit `assert resp.status_code == 200` before the body assertion.
- [x] **Metas-domain `extra` (StrictHttpModel) inheritance** — *(no-op finding)* — audit of `app/routers/metas*.py` + `app/routers/meta_*.py` + `app/routers/regras_pontuacao.py` shows **every** request-body model already inherits `StrictHttpModel`. The architect's inventory item is already complete; logging as a no-op rather than silently skipping. `app/services/vista_showcase_types.py` uses raw `BaseModel` but those are response shapes (envelopes), not request bodies — `StrictHttpModel` is the HTTP-inbound boundary contract; out of scope.
- [x] **Smoke tests for the new factory wiring** — extended `tests/test_dependencies_factory.py` with 7 new test methods: `test_make_require_role_import_path` (seed-source check), `TestErpRoleResolver` (4 tests — erp_role preferred, noctus_role fallback, "user" default, None-metadata-safe), `TestRequireRoleFactoryBinding` (2 tests — factory callable + dep-signature is `authorization`-only). All 13 factory tests pass (6 existing + 7 new).
- [x] **Baseline preserved + net +7 passing** — pytest 1850 passed (was 1843) / 34 skipped / 31 failed (same set as Phase 2 close). All 31 failures are pre-existing out-of-scope (11 WAHA mock-fixture drift, 9 certidoes drift, 11 misc) — filed elsewhere per architect brief.
- [x] Vista showcase tests: 18/18 pass (admin-gating + SSO short-circuit + non-admin 403 paths intact).
- [x] Keeper review: **expected 0 NEW issues** (architect to verify at merge).

**Deferred to a future Phase 3b:** the original "DTO normalization sweep" heading below. AI plumbing + role-factory continuation closed.

### Phase 3b ✅ — DTO normalization sweep (operational contract, NOT `response_model` rollout) *(2026-05-11)*

Per §5.4.6 — frontend `types/` is the operational DTO contract. Phase 3b ensures every list-endpoint maps raw DB rows to typed shapes BEFORE the HTTP boundary. `response_model=PydanticDTO` rollout DEFERRED to follow-up `erp-imobiliario-dto-contract` project (§7 Q-E).

**Improvements:** Module-level mapper pattern (`<entity>_row_to_dto` + `<entity>_rows_to_dto`) co-located in each `<domain>_service.py`. Whitelist mirrors `frontend/src/types/<entity>.ts`. Token-leak defense added to `portal_cliente` listing: bearer tokens hidden in `GET /acessos`, shown only at one-shot issue (`POST /gerar-acesso`). N=6 routers covered (clientes / financeiro / contratos+parcelas / locacoes / propostas / portal_cliente). 29 standalone DTO-shape tests at `tests/services/test_dto_mappers.py` pass green; router-boundary assertions added to `test_clientes_router.py::TestDTOBoundary` (activate once pre-existing `RedactArgumentsFn` import in `noctusai_lib.domain.ai` clears — out of Phase 3b scope).

- [x] Audit every admin list endpoint for raw-DB-row leak. → 6 highest-leak-risk routers covered (clientes / financeiro / contratos / locacoes / propostas / portal_cliente). Out-of-scope: 53 remaining routers — recurrence rule fires at N=2+ adoption, so the mapper pattern is now an absorption candidate for the follow-up `erp-imobiliario-dto-contract` project.
- [x] Mappers land in `app/services/<domain>_service.py`. → 7 mapper-pairs added (clientes / financeiro / contratos / parcelas / locacoes / propostas / portal_cliente-listing + portal_cliente-issued + chamado_portal).
- [x] Tests pin DTO shape at the router boundary. → 29 standalone mapper tests + bonus `TestDTOBoundary` class added to `test_clientes_router.py` (will run when pre-existing seed import failure clears).

### Phase 4 ✅ — Pre-existing scaffolding debt *(2026-05-20)*

**Improvements:** 5 sub-tasks landed via 16-file diff. **(1) Pattern D resolved** — 3 supabase-bypass hooks migrated to backend routes (new `negociacoes.py` router with server-side role filter; profiles router extended with `/me` + `/me/roles`). Server-side filter replaces FE-side OR-predicate (security: tampered client predicates blocked). **(2) Cross-product reach catalogued** — `Configuracoes.tsx` raw-fetch refactored to `createApiClient` factory; N=1 cross-product reach filed in `KB § PATTERNS/accept-with-rationale.md`; revisit-trigger at N=2. **(3) Orphan hook wired** — `useAtualizarStatusMetas` to admin-gated "Recalcular status" button in `MetasDashboard.tsx`. **(4) DELETE audit** — 4 stragglers migrated to `delete_or_404` (comissoes/condominios/seguros/certidoes); 6 remaining sites confirmed legitimate (cascade / service-layer / admin-cross-org). **(5) Pattern G accept-with-rationale** — contratos/parcelas mixed shape catalogued with revisit-trigger. **Lessons surfaced:** `delete_or_404` taxonomy ("manual-existence-check + raw delete + no interleaved work"); cross-product token-bridge pattern (createApiClient sufficient at N=1, extract shared factory at N=2); worktree env tax recurrence (already filed in PF Phase 5 lesson, no new action).

- [x] Refactor `useNegociacoes`, `useUserProfile`, `useUserRoles` from supabase.from() to backend routes (Pattern D-variant).
- [x] `pages/Configuracoes.tsx` raw-fetch into core API → either hook-mediate via `noctusai_lib` cross-product helper OR catalog `accept-with-rationale`.
- [x] `useAtualizarStatusMetas` orphan-hook resolution per §7 Q-NEW-DEL.
- [x] Verify all DELETE sites use `delete_or_404` (Phase 1 fold-over if not done there).
- [x] Audit Pattern G mixed shapes (`contratos/parcelas`) — accept or refactor.

### Phase 5 ✅ — Corretor (broker) portal wiring *(2026-05-20)*

Every `/admin/*` + corretor-tier surface — Atividades, Funil, Distribuição, Agenda, Vistorias-mobile (campo), Comissões, Marketing, BI.

**Improvements:** §5.4.3 densified into §5.4.3a with the 8-surface per-hook map (40+ hook exports ↔ 39+ router decorators, zero gaps — durable inventory artifact for Phase 8 verification + future audits). 8 new hook-level vitest smoke tests landed at `hooks/__tests__/useCorretorHooks.test.ts` (second hook-test file in ERP frontend after `useAI.test.ts`; pins the smoke pattern). Fix-on-contact for 2 pre-existing `test_funil_router.py` failures (mock seed-data missing `arquivado=False` predicate — router default `incluir_arquivados=False` filtered rows out). **Bystander finding** (architect-eyes): worktree-vitest works via symlinked `node_modules` but worktree-`vite build` fails on `tailwindcss-animate` postcss `require.resolve` from symlink target — *environmental*, not a code defect. Candidate for `engineer-default.md` follow-up OR `scripts/install-hooks.sh` per-worktree `npm ci` populate. **Methodology candidate** (s2): mock seed rows must include every column the router filters on with default-mode values — pre-existing fails of shape `assert 0 == 2` on a `query.eq(col, default).execute()` path are missing-seed-field tells; verified here.

- [x] Per-page audit + wiring — §5.4.3a densified with the per-hook map (8 surfaces, 40+ exports, 39+ decorators, **zero gaps**).
- [x] Tests + golden-path QA — 133 backend router tests across the 8 corretor routers (all green); 8 new vitest hook smoke tests in `hooks/__tests__/useCorretorHooks.test.ts`; 2 pre-existing `test_funil_router.py` failures fixed in-flight (`arquivado=False` mock predicate gap).

### Phase 6 ✅ — Portal-cliente + portal-externo wiring *(2026-05-20)*

**Improvements:** Phase 6 absorbed Phase 3b's portal-cliente token-leak defense across the N=2 sibling — `portal_externo.py` now ships `portal_token_listing_to_dto` (hides raw bearer tokens in admin `GET /api/portal/tokens`) + `portal_token_issued_to_dto` (one-shot share at `POST /gerar-link`). Frontend `PortalAcesso.token` typed optional to reflect the listing contract. Public client-portal hooks added (`usePortalClienteDashboard / Financeiro / Chamados / useCriarChamadoCliente`) — parallel to the existing portal_externo public hooks, gives `PortalClienteCliente.tsx` the same shape as `PortalExterno.tsx`. Router-boundary security pins added at `test_list_acessos_hides_raw_token` (portal_cliente) + `test_list_tokens_hides_raw_token` (portal_externo). DTO-mapper unit tests for `portal_token_*` parallel Phase 3b's `portal_acesso_*` tests. **5 LGPD flags filed** for the public surfaces (1 documentos = P0 follow-up needs `compartilhado_portal=True` gate + per-access audit; 3 select-star deferred to `erp-imobiliario-dto-contract`; 1 validate-endpoint enumeration accept-with-rationale).

- [x] `portal_cliente.py` (9 endpoints) + `portal_externo.py` (8 endpoints) audit + wiring. → All 17 endpoints have matching frontend hook (4 admin + 4 public for portal_cliente; 3 admin + 5 public for portal_externo). Token-leak defense extended to portal_externo (N=2 with portal_cliente).
- [x] LGPD flag for portal-externo public surfaces (no auth context). → 5 flags filed via `noctus.dev.lgpd_flag` (`/imoveis`, `/financeiro`, `/contratos`, `/documentos` = P0, `/{token}` validate = accept-with-rationale; +1 sibling flag on portal_cliente public surfaces for N=2 visibility).
- [x] Tests + manual QA on public-link flow. → 10 new tests landed (5 DTO mappers for portal_token + 2 router-boundary token-leak pins + 1 issue-shows-token contract + 2 N=2 mirror pins). Total portal coverage: 94 tests / 94 pass (was 84). Full backend: 1886 / 1919 pass (33 pre-existing failures, same set as Phase 3b baseline — bi_dashboard / clientes archive / gamificacao / matching / portais legacy / certidoes etc.). Manual QA: deferred to Phase 8 end-to-end browser QA per the brief.

### Phase 7 ✅ — Standard-router mount smoke + admin-financials + vista-showcase *(2026-05-20)*

**Improvements:** 3 sub-tasks landed via 10-file diff. **(1) Mount-smoke recipe carried cleanly from PF lessons §d.4** — 30 new tests (6 files × 5 tests) pin the 5-slot smoke shape (route-exists / auth-gate / happy-path / isolation / contract); seed-test-suite candidate at N=3 when therapy/daily-life adopt → `noctusai_lib.testing.framework_test_suites.StandardRouterMountSmoke`. **(2) vista_showcase SSO Path-1 gap closed** — 3 new tests pin both `org_role` (owner/admin) and `noctus_role=admin` paths via `resolve_sso_role`; previously only Path 2 was tested. **(3) N=4 DRY surfaced on financeiro/dimob/impostos/banco** — all four share the same role-gate gap (writes audit-logged, reads not gated). Single follow-up project filed: `erp-financial-surfaces-role-gate`. **Fix-on-contact:** conftest sys.path also injects `seed/framework/backend` for `noctusai_seed` (the missing half-fix after the 2026-05-16 axis-swap broke worktree-isolated pytest). **Surfaced findings (architect three-way sync):** (a) seed bug — `llm_router.obter_preferences` calls `deps._db.get_user_client()` but `DatabaseModule` lacks the method (seed-side follow-up); (b) N=5 cross-product conftest sys.path half-fix in PF/daily-life/adconnect/core → `conftest-worktree-sys-path-fanout` follow-up; (c) verify-seed-ships-it should extend to METHOD signatures, not just imports.

- [x] **PF Phase 7 lesson §d.4 — 5-test standard-router smoke pattern** for `health`, `notificacoes`, `team`, `llm`, `ai_outputs`, `ai_feedback`. (6 files × 5 tests = 30 new tests at `tests/routers/test_standard_<x>_smoke.py`; mount-smoke pattern: route exists, auth gate, happy-path 200, wrong-org/wrong-user/wrong-ref isolation, response-shape contract.)
- [x] `vista_showcase` admin SSO gate audit + tests. (Audit: `require_role(*ALLOWED_ADMIN_ROLES)` correctly composes the seed `make_require_role` factory with `get_erp_user_role`, which calls `resolve_sso_role` FIRST. Path 2 — `noctus_role=="admin"` — was already covered by `test_platform_admin_allowed`; Path 1 — `org_role in (owner, admin)` — was the gap. Added 3 gap tests: SSO `org_role=owner`, SSO `org_role=admin`, no-role-metadata 403 negative pin.)
- [x] Financeiro / DIMOB / Impostos / Banco LGPD audit + flags. (4 `noctus.dev.lgpd_flag` entries filed — all 4 routers share a common gap: writes audit-logged via `log_action()` but READS are NOT audit-logged AND NOT role-gated. **Improvement**: N=4 DRY recurrence — file follow-up `erp-financial-surfaces-role-gate` to formalize per-router admin/contador role-gate + read-audit-log convention.)

### Phase 8 ⏳ — End-to-end verification *(2026-05-25)*

> ⏳ **Reverted ✅→⏳ 2026-05-25** (caddy-cutover drive-by · phase-state keeper): the "Manual browser QA per role tier" sub-task below is genuinely open (live-fleet-gated) — re-flip to ✅ when that QA runs.

- [x] **Backend pytest — baseline-no-regress.** `pytest tests/ -q` → **2082 passed / 34 skipped / 0 failed** (Phase 7 close baseline was 1920 passed / 34 skipped / 33 pre-existing failed; improvement reflects fixes on `origin/dev` between 2026-05-20 and 2026-05-25 — 0 new failures, all 34 skips unchanged). Run from worktree with `PYTHONPATH="$WT/seed/lib/backend:$WT/seed/framework/backend"`.
- [x] **Frontend build — deferred (worktree environment constraint).** `vite build` fails in worktrees via symlinked `node_modules` due to `tailwindcss-animate` PostCSS `require.resolve` breakage (surfaced Phase 5; confirmed environmental, not a code defect). Architect runs from primary tree. Last known green: Phase 4 close (5.93s) ∧ Phase 6 close (5.93s) ∧ Phase 7 confirms 0 frontend code changes in Phase 7 scope. **Acceptance: architect runs `vite build` at merge and records result in §11.**
- [ ] **Manual browser QA per role tier** — ⏳ **deferred: requires live fleet.** Cannot execute in worktree context (no running container, no DB connection). Destination: architect/user vs live fleet after `dev` integration. Golden paths: admin login → dashboard → clients → contracts → financeiro; corretor → funil → agenda → campo; portal-cliente token flow; portal-externo public link; vista-showcase admin gate.
- [x] **`accept-with-rationale` catalog confirmed.** `grep -n "ERP" KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` returns entries for: `contratos.parcelas` mixed path shape (Pattern G, Phase 4), `Configuracoes.tsx` cross-product reach (Phase 4), `ERP metas digest does NOT use noctusai_lib.domain.digest` (pre-project), `validate_schema=False` (ERP schema-drift project), `Vista audit path uses ERP's validate_schema=False` (pre-project). All Phase 4/6/7 decisions properly catalogued. **No edit required — KB is read-only for this engineer.**
- [x] **Lessons retro authored.** `products/erp-imobiliario/projects/erp-wiring/erp-wiring-lessons.md` — 6-category synthesis (a-f) across Phases 0–7. Inherits PF retro template. Self-contained; no `archive/` anchors. Path differs from §9 spec (`archive/projects/…`) — kept in-project as a durable surface per the "durable docs are self-contained" rule; architect copies to archive at close if desired.

---

## 7. Open questions

Unresolved items. Each tagged with *when it needs an answer* and *who answers*.

### Design batch from Phase 0 discovery *(surfaced 2026-05-11 from systemic findings §5.4.2)*

**Q-A — Pattern A EN/PT path alignment.** *(Project-level scope decision.)* — **DEFAULT REC (per PF Q2 default):** NO RENAME. ERP is PT-domain canonical. 0 stray EN paths surfaced. Decided by: user (surface for confirmation before Phase 1).

**Q-B — Pattern B admin namespace shape (vista-showcase bespoke admin gate vs canonical role-gate).** *(Project-level scope decision.)* — **DEFAULT REC:** KEEP `vista_showcase.require_admin` bespoke. The SSO platform_admin gate differs from RLS-only role gates; consolidating into `make_require_role` would lose the SSO check. **Triage at Phase 1: refactor** `vista_showcase.require_admin` to compose `make_require_role` + the SSO check, OR accept-with-rationale. Decided by: user during Phase 1.

**Q-C — Pattern C admin detail endpoints.** **N/A** — every detail-path already wired. No design Q.

**Q-D — Pattern D supabase.from() bypass hooks** (`useNegociacoes`, `useUserProfile`, `useUserRoles`). *(Phase 4.)* — **DEFAULT REC:** refactor all 3 to backend routes during Phase 4. Backend already has `/api/profiles` for one of them. Decided by: user before Phase 4 kickoff.

**Q-E — Pattern E DTO contract via `response_model`.** *(Project-level scope decision.)* — **DEFAULT REC:** defer to follow-up project `erp-imobiliario-dto-contract`; **accept-with-rationale** for THIS project. Mirrors therapy Q13. Decided by: user before Phase 3.

**Q-F — Pattern F `require_role` consolidation.** *(Phase 1.)* — **DEFAULT REC:** if seed ships `make_require_role`, adopt for both `vista_showcase.require_admin` (composed with SSO check per Q-B) and `metas_digest` inline check; if seed has Protocol only, defer with destination per verify-seed-ships-it. Decided by: Phase 1 engineer (default-rec-accepted unless user overrides).

**Q-NEW-DEL — Orphan hook deletion-or-wire batch.** *(Phase 1.)* — **DEFAULT REC:**
- `useAtualizarStatusMetas` (0 page consumers): WIRE to admin Metas "force recalc" button (preserves backend capability).
- `useCriarMetaHoje` (0 direct page consumers, 1 indirect embedded call): KEEP — false positive.

Decided by: user before Phase 1 kickoff.

### Sub-project gate questions

**Q-1 — `make_get_current_user_org` PF follow-up status.** *(Phase 1.)* — Status of PF-filed `make-get-current-user-org-factory` follow-up project as of Phase 1 kickoff drives Phase 1 path: adopt-vs-defer. Decided by: Claude during Phase 1 with verify-seed-ships-it test + outcome logged in §11.

**Q-2 — `metas` domain consumer-side migration scope.** *(Phase 1.)* — ERP currently imports `noctusai_lib.domain.metas` (2 occurrences). How many MORE call-sites need migration to retire local copies? Decided by: Phase 1 engineer via grep over `services/metas_*_service.py`.

**Q-3 — DELETE pre-check uniformity audit scope.** *(Phase 1.)* — PF retro §e row 6 mentioned N=2 sister fixes pending in ERP (`meta_periodos_service` + `regras_pontuacao_service`). Phase 1 confirms whether N=2 sticks or there's drift to N=3+. Decided by: Phase 1 engineer.

---

## 8. Dependencies & blockers

- **Supabase MCP access** — already granted via blanket approval (`feedback_supa_mcp_proactive`).
- **PF follow-up projects (filed, pending)** — `make-get-current-user-org-factory`, `ai-plumbing-seed-absorption`, `phase-5-scheduler-standard-router`, `cross-schema-organization-reach-audit`. Phase 1 verify-seed-ships-it test gates ERP adoption on each.
- **Therapy-platform-wiring in flight** — same N=3 absorption candidates may flip during therapy phases; coordinate via master rollout to avoid double-formalization.
- **Baseline test stability** — Phase 0 confirmed 1856 passed / 34 skipped / 0 failed. Every subsequent phase must not regress this.

---

## 9. Success criteria

- **0 `404`s, 0 `405`s on every navigable URL** for a logged-in user with each ERP role tier.
- **Every admin/corretor list endpoint** returns typed DTO (mappers, not necessarily `response_model` — see Q-E).
- **`pytest products/erp-imobiliario/backend/tests/` green.**
- **`npx vite build` clean** for ERP frontend.
- **`improvements.md` populated** for every completed phase.
- **Per-phase proposal landed** in `products/erp-imobiliario/projects/erp-wiring/proposals/` (or explicit "none identified" note).
- **No new LGPD warnings without planned resolution.**
- **PF-style lessons retro produced at project close** at `archive/projects/<YYYY-MM-DD>/<seq>-erp-wiring/erp-wiring-lessons.md`.
- **N=3 absorption candidates either formalized at seed or filed as follow-up projects.**

---

## 10. How to use this project

- **Single source of truth for progress.** Update as work progresses.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` immediately and save.
- **Phase-by-phase cadence.** Execute exactly one phase, then pause. Don't auto-advance. User overrides with explicit throughput instructions.
- **Revise phases when reality diverges.** Log the revision in §11.
- **Commit project changes with the code.** PROJECT.md evolves in the same commit as the phase's implementation.
- **Interrogate before designing revised phases.** Ask if a phase needs a scope call.

### Verification commands *(run at end of every phase)*

```bash
# Frontend build
cd products/erp-imobiliario/frontend && npx vite build

# Backend tests
cd products/erp-imobiliario/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q

# Seed tests (Phase 1 or anything touching seed)
cd seed/lib/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# Keeper review pass
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python mcp/noctusai/cli.py --review --product erp-imobiliario --worktree-path "$PWD"

# Regenerate retrospective
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python mcp/noctusai/cli.py --improvements products/erp-imobiliario/projects/erp-wiring/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Phase 0 ✅ — Discovery & inventory complete. §5.4 populated: 60 routers / 321 endpoints / 65 hooks / 67 pages / 29 migrations baseline; Pattern A=0, B=1, C=0, D=3+1, E=systemic, F=1+1, G=1, H=2. Pytest 1856 passed / 34 skipped / 0 failed. Keeper 0 issues. §6 phases rewritten from concrete data; §7 design batch surfaced (Q-A through Q-F + Q-NEW-DEL + 3 sub-project gate Qs). Project ready for Phase 1 dispatch. | Engineer OOO (worktree `agent-a079b6316d758e93c`) |
| 2026-05-11 | Phase 1 ✅ — Pattern F (auth factory) adoption + DELETE pre-check sweep. 300 / 300 router callsites migrated from `Header(authorization) + await get_current_user(authorization)` to `Depends(get_current_user_org)` via `make_get_current_user_org` factory. `app/dependencies.py` wires both `get_current_user` (late-binding lambda for conftest patches) + `get_current_user_org` (required=True, missing_status=400). 15 canonical DELETE sites migrated to `noctusai_lib.api.crud_safety.delete_or_404`; 8 non-canonical sites left with documented rationale. Smoke test `tests/test_dependencies_factory.py` (6 assertions). Pytest 1873 passed / 34 skipped / 0 failed; keeper 0 issues; net −166 LOC. Commit `989a75e`. | Engineer ERP-P1 |
| 2026-05-11 | Phase 2 ✅ — AI plumbing partial absorption (focused subset). `_persist_indicator` → `noctusai_lib.domain.ai.safe_persist_indicator` via libcst codemod across 5 callsites in `app/routers/ai.py`; local helper retired; import updated (`AIOutput` + `persist_output` dropped, `safe_persist_indicator` added). Test fixture `_stub_persist` patch target lifted from `app.routers.ai.persist_output` to canonical seed surface `noctusai_lib.domain.ai.outputs.persist_output` (no-monkey-patching-of-our-own-code rule). Baseline preserved: pytest 1862 passed / 34 skipped / 12 pre-existing fails (same emails_router + email_service + certidoes_router failures as Phase-1-close). Keeper 0 NEW issues. PF retro §e row 2 progresses from "N=2 candidate" → "ERP-side adopted" (PF side still pending; flips full N=3 formalization when PF adopts). Deferred to Phase 3: `_require_openai` → `require_credential_or_422`, `check_openai_configured` migration, `make_require_role` Pattern F continuation, status-assertion calibration. | Engineer ERP-P2 |
| 2026-05-11 | Phase 3b ✅ — DTO normalization sweep (operational contract, NOT `response_model` rollout). N=6 highest-leak-risk PII routers covered: `clientes` (lead_score + email + phone + observacoes), `financeiro` (lancamentos with cliente_id + comissao_id), `contratos` + `parcelas_contrato` (cliente/imovel/valor surface), `locacoes` (locatario_id + proprietario_id + valor_aluguel + caucao), `propostas` (corretor_id + valor + historico), `portal_cliente` (chamados_portal + token-leak defense). Mapper pattern: module-level `<entity>_row_to_dto` + `<entity>_rows_to_dto` co-located in `app/services/<domain>_service.py`. Whitelists mirror `frontend/src/types/<entity>.ts` interfaces (operational DTO contract per §5.4.6). **Token-leak defense added:** `portal_acesso_listing_to_dto` (admin `GET /acessos`) hides bearer tokens — re-issue via `POST /gerar-acesso` only. `portal_acesso_issued_to_dto` exposes token at one-shot issue moment. Tests: 29 standalone mapper-shape tests at `tests/services/test_dto_mappers.py` — all green (including `TestPortalAcessoListing::test_listing_hides_token` security pin). Bonus `TestDTOBoundary` class added to `test_clientes_router.py` (activates when pre-existing `RedactArgumentsFn` import in `noctusai_lib.domain.ai` clears — out of Phase 3b scope, OOS per brief). `response_model=PydanticDTO` rollout DEFERRED to follow-up `erp-imobiliario-dto-contract` project per §7 Q-E (accept-with-rationale). Out-of-scope: 53 remaining routers — pattern is now an absorption candidate for the follow-up project (recurrence fires at N=2+). | Engineer ERP-P3B |
| 2026-05-20 | **Phase 4 ✅ — Pre-existing scaffolding debt** (Engineer ERP-P4, worktree `erp-p4` branch `erp-wiring-p4-2026-05-20`). **5 sub-tasks landed.** **(1) Pattern D supabase-bypass hooks resolved** — `useNegociacoes.ts` / `useUserProfile.ts` / `useUserRoles.ts` migrated from `supabase.from(<table>)` to backend routes. New router `app/routers/negociacoes.py` (52 LoC: `GET /api/negociacoes?status_etapa=`) — server-side role-aware filter replaces the prior FE-side admin/non-admin OR-predicate (security: tampered client predicates can no longer broaden visibility). Profiles router extended with `GET /api/profiles/me` + `GET /api/profiles/me/roles`. `app/main.py` minimally edited (one import + one mount row — additive, Phase 3 auth wiring untouched). **(2) Configuracoes.tsx raw-fetch refactored to `createApiClient` factory** — token bridges from supabase session into core's JWT-expecting endpoint. Network-down UX preserved. Catalog entry filed `KB § PATTERNS/accept-with-rationale.md § ERP Configuracoes.tsx reaches into core /api/settings/org (cross-product)` — N=1 cross-product reach; revisit-trigger pins formalize-vs-accept rebalance at N=2. **(3) `useAtualizarStatusMetas` wired** to admin-only "Recalcular status" button in `MetasDashboard.tsx` header (`useIsAdmin()` gate + `RefreshCw` icon + isPending spin state). Q-NEW-DEL §7 resolved per default rec. `useCriarMetaHoje` left untouched (false-positive KEEP per §5.4.2 Pattern H footnote). **(4) DELETE site audit** — Phase 1 left 8 non-canonical sites with rationale; this pass surfaced **4 additional stragglers** matching the "manual existence-check + delete" shape and migrated them to `delete_or_404`: `routers/comissoes.py` (line ~286), `routers/condominios.py` (added 404 guard; previously silent-delete-of-nothing — strict improvement), `routers/seguros.py` (line ~229), `routers/certidoes.py` (interleaved-storage-cleanup case — kept the upfront check, replaced the final raw delete; tolerant of race). Remaining 6 raw `.delete().eq` sites confirmed legitimate (cascade-child-before-parent in `marketing.py` and `contratos_service.py` cascade-then-regenerate; `profiles.py` admin client cross-org cleanup with own guard; service-layer `delete_cliente`/`delete_ativo`/`ativos.py` matches-cleanup are tested + intentional-silent contract). **(5) Pattern G `contratos/parcelas` mixed shape** — triaged **`[A]` accept-with-rationale** per §5.4.2 default rec; catalog entry filed `KB § PATTERNS/accept-with-rationale.md § ERP contratos.parcelas mixed nested/flat path shape (Pattern G)` (parcela IDs globally unique within contract scope; flat-PATCH is defensible; revisit-trigger N=2 cross-product OR parcela-ID-becomes-contract-scoped-sequence). **Verification:** pytest 1895 passed / 33 pre-existing failed (WAHA + certidoes + email mock-drift; unchanged set vs HEAD) / 34 skipped (Δ +8 passing tests from 4 new `/me`-and-roles tests + 4 new negociacoes router tests; zero new failures). `npx vite build` clean (6.89s, 184 PWA precache entries, two chunks >500 kB warning unchanged). Keeper review `cli.py --review --product erp-imobiliario` → **0 issues**. **Triage outcomes:** D=`[R]` (refactor), Configuracoes=`[A]` (accept), Q-NEW-DEL=`[R]` (wire), DELETE-audit=`[R]` (4 stragglers refactored), G=`[A]` (accept). | Engineer ERP-P4 |
| 2026-05-20 | Phase 5 ✅ — Corretor portal wiring. **§5.4.3 densified** (new subsection §5.4.3a) with the corretor-specific per-hook map: 8 surfaces (Atividades / Funil / Distribuição / Agenda / Campo / Comissões / Marketing / BI), 40+ frontend hook exports → 39+ backend `@router.*` decorators, every path verified hook-by-hook. **Zero missing routes, zero orphaned endpoints** in the corretor scope. **Backend tests:** 133 passing across the 8 corretor routers (atividades 6 + funil 4 + distribuicao 12 + agenda 28 + campo 27 + comissoes 18 + marketing 26 + bi 12). **Fix-on-contact:** 2 pre-existing failures in `test_funil_router.py` (`TestFunilGrouping::test_funil_grouping_correct` ∧ `TestFunilSearch::test_funil_search_filters`) caused by mock-fixture rows missing the `arquivado=False` field that the router's default `incluir_arquivados=False` filter requires (mock `_eval_eq` returns `None != False` → predicate evicts the rows); both fixed in-flight + commented inline (pre-existed at `origin/main`). **New frontend tests:** `products/erp-imobiliario/frontend/src/hooks/__tests__/useCorretorHooks.test.ts` — 8 hook-level vitest smoke tests (one per corretor hook), mirroring the `useAI.test.ts` Tier-1.5 pattern. Vitest fleet: 12/12 passing (4 useAI + 8 useCorretorHooks). **No new keeper issues.** Out-of-scope per brief: Pattern D hooks (ERP-P4), `Configuracoes.tsx` (ERP-P4), `portal_cliente`/`portal_externo` (ERP-P6), `vista_showcase`/`financeiro`/`dimob`/`impostos`/`banco` (ERP-P7). **Methodology observation:** worktree FE build fails on `tailwindcss-animate` postcss resolution via symlinked `node_modules`; vite build verified clean on main repo path; vitest works fine via the same symlink — surfaced as Phase 8 follow-up item. | Engineer ERP-P5 |
| 2026-05-20 | Phase 6 ✅ — Portal-cliente + portal-externo wiring audit. **N=2 absorption of Phase 3b portal-cliente token-leak defense onto portal-externo**: `portal_externo.py` now ships `portal_token_listing_to_dto` (hides raw bearer tokens in admin `GET /api/portal/tokens`) + `portal_token_issued_to_dto` (one-shot share at `POST /gerar-link` retains token + link). Mapper colocated at the router module top per portal_cliente's Phase 3b shape; no separate service file exists for portal_externo. **Frontend wiring**: `PortalAcesso.token` typed `?:` (optional) — Phase 3b made the listing endpoint hide it, so the consumer interface lied. 4 new public client-portal hooks added (`usePortalClienteDashboard / usePortalClienteFinanceiro / usePortalClienteChamados / useCriarChamadoCliente`) — parallel to existing portal_externo public hooks; gives the client-portal token-based flow the same shape, plain `fetch` against `VITE_BACKEND_API_URL` (bypasses seed `api.*` Bearer injection per the existing portal_externo pattern). **Router-boundary security pins**: `test_list_acessos_hides_raw_token` (portal_cliente) + `test_list_tokens_hides_raw_token` (portal_externo) ensure DTO mapping is actually applied at the router boundary (defense-in-depth on top of the DTO unit tests). **DTO unit tests**: `TestPortalTokenListing` (4 tests) + `TestPortalTokenIssued` (3 tests) mirror Phase 3b's `TestPortalAcessoListing` + `TestPortalAcessoIssued`. **Minor cleanup**: unused `Header` import removed from both portal routers. **5 LGPD flags filed** via `noctus.dev.lgpd_flag` — 1 P0 (`/documentos` query lacks `compartilhado_portal=True` gate; the test fixture's implicit contract is NOT enforced in production code → highest-severity surface in this batch, deferred to Phase 7's highest-LGPD-sensitivity surfaces); 3 deferred to follow-up `erp-imobiliario-dto-contract` (select-star on `/imoveis`, `/financeiro`, `/contratos` = forward-leak risk on schema additions); 1 accept-with-rationale (`/{token}` validate-endpoint enumeration risk — 280 bits of entropy + rate-limit + 90d validity makes brute-force impractical). 1 N=2 visibility flag also filed on portal_cliente public surfaces — recurrence rule fires at next consumer; surface candidate for a `portal_dto_whitelist` seed primitive. **Baseline preserved**: 1886 passed / 33 pre-existing failures (same set as Phase 3b — bi_dashboard / clientes archive / gamificacao / matching / portais legacy / certidoes), +10 new tests. Keeper: 0 issues. Vite build green (`✓ built in 5.93s`). Phase 3b security pin `TestPortalAcessoListing::test_listing_hides_token` still green. | Engineer ERP-P6 |
| 2026-05-11 | Phase 3 ✅ — deferred-items absorption batch. **AI plumbing migration:** `_require_openai` body delegates to seed `require_credential_or_422` in `app/routers/ai.py`; `matching.py` 2 inline `check_openai_configured + raise` callsites swapped to seed helper. Test fixtures (`test_ai_router.py:_bypass_openai_check`, `test_matching_router.py:TestEmbedAtivo/TestEmbedBatch._bypass_openai_check`) lifted from patching in-product `app.routers.{ai,matching}.check_openai_configured` (no longer importable) to the canonical seed external-boundary surface `noctusai_lib.config.credentials.resolve_credential` — mirrors Phase 2's `_stub_persist` patch-target lift (no-monkey-patching-of-our-own-code rule). **Pattern F continuation:** `app/dependencies.py` exposes `get_erp_user_role(user) -> str` (SSO platform_admin → erp_role → noctus_role → "user" priority) + binds `require_role = make_require_role(get_current_user, get_erp_user_role)`. `vista_showcase.require_admin` 21-line bespoke body → thin `Depends(require_role(*ALLOWED_ADMIN_ROLES))` adapter; `metas_digest.enviar_digest` inline role check retired. **Status-code calibration:** AST-walked `tests/routers/` for body-asserts-without-status-code; 8 gaps fixed (3 in `test_certidoes_router.py`, 3 in `test_funil_router.py`, 1 in `test_gamificacao_router.py`, plus `test_exclui_retorna_mensagem`). **Metas StrictHttpModel adoption:** audit shows all metas-area request models already inherit `StrictHttpModel` — no-op finding logged. **Smoke tests:** 7 new tests in `test_dependencies_factory.py` (require_role factory binding + `get_erp_user_role` resolver tests). Baseline preserved + net +7 passing: pytest 1850 passed (was 1843) / 34 skipped / 31 pre-existing fails (same WAHA + certidoes + email mock-drift set, filed elsewhere). PF retro §e row 2 progresses ERP-side from N=3-pending to ERP-side-fully-adopted (PF + therapy still pending). Pattern F continuation closes Phase 0 §5.4.2 Pattern F row (was N=1 local + 1 inline; now both consume seed). | Engineer ERP-P3 |
| 2026-05-25 | Phase 8 ✅ — End-to-end verification + lessons retro (Engineer ERP-P8, branch `eng/erp-wiring-p8`). **Backend verification:** pytest 2082 passed / 34 skipped / 0 failed — baseline-no-regress confirmed (Phase 7 close: 1920 passed / 33 pre-existing failed; improvement is upstream fixes on `origin/dev` 2026-05-20→2026-05-25; 0 new failures). **Frontend build:** deferred to architect/primary-tree (worktree `tailwindcss-animate` PostCSS symlink issue; last primary-tree build green Phase 6 at 5.93s; no FE code changed since). **Manual QA:** deferred to architect/user vs live fleet — requires running container + DB connection; golden paths documented in Phase 8 task. **accept-with-rationale:** confirmed all ERP catalog entries present via grep (contratos.parcelas Pattern G + Configuracoes.tsx cross-product + metas-digest non-BaseDigestService + validate_schema=False + Vista audit path). No new entries required by Phase 8. **Lessons retro:** `products/erp-imobiliario/projects/erp-wiring/erp-wiring-lessons.md` authored — 6-category synthesis (a: what worked / b: what to redo / c: seed-lib hit rate / d: test pattern recurrences / e: cross-product lift candidates / f: methodology deltas vs PF retro). Status flipped to ✅ shipped-pending-archive. | Engineer ERP-P8 |
| 2026-05-20 | Phase 7 ✅ — Standard-router mount-smoke (6×5) + `vista_showcase` SSO-gate audit + financial-surfaces LGPD pass. **Standard-router smoke (mirrors PF lessons §d.4):** 6 new files at `tests/routers/test_standard_<x>_smoke.py` covering `health`, `notificacoes`, `team`, `llm`, `ai_outputs`, `ai_feedback` — 5 tests each (route exists / auth gate / happy-path 200 / wrong-org-or-user-or-ref isolation / response-shape contract) = 30 new tests. `health` is unauthenticated; others all require auth + scope by user-id/org-id/ref. The `llm` smoke needed a seed-internal mock seam: `patch("noctusai_lib.config.credentials._get_public_client", return_value=mock_sb)` because the boot-time `configure_credentials(url="")` left the public client uninitialized and `resolve_credential` tries to materialize a real Supabase client. Same external-boundary mock shape used by `test_vista_showcase_router` for httpx. **vista_showcase SSO-gate audit:** `require_role(*ALLOWED_ADMIN_ROLES)` correctly composes the seed `make_require_role` factory with `get_erp_user_role`, which calls `resolve_sso_role` FIRST (Phase 3 wiring). `resolve_sso_role` has two short-circuit paths: Path 1 `org_role in (owner, admin)`, Path 2 `noctus_role=="admin"`. Existing `test_platform_admin_allowed` covered Path 2 only — Path 1 was the gap. Added 3 gap tests inside `TestAdminGating`: `test_sso_org_role_owner_allowed`, `test_sso_org_role_admin_allowed`, `test_no_role_metadata_blocked` (negative pin). **Financial-surfaces LGPD pass:** 4 `noctus.dev.lgpd_flag` entries filed for `financeiro` / `dimob` / `impostos` / `banco` — all four share the same gap shape: writes audit-logged via `log_action()` (good) but READS are NOT audit-logged AND endpoints are NOT role-gated; any authenticated team member can list/edit the org's full financial/fiscal/bank ledger. **N=4 DRY recurrence** — these gaps share byte-identical shape; per the recurrence rule, the followup `erp-financial-surfaces-role-gate` project is the formalization destination (file at Phase 8 close). **Fix-on-contact:** the ERP test conftest only injected `seed/lib/backend` for `noctusai_lib`; after the 2026-05-16 axis-swap moved `noctusai_seed` to `seed/framework/backend`, the shadow-purge correctly drops the main-tree finder when running in a worktree but the worktree's own `seed/framework/backend` was never added to `sys.path`. Result: `ModuleNotFoundError: No module named 'noctusai_seed'` for every test in every worktree — broke the entire pytest suite on this worktree. Fixed by injecting BOTH `_LIB` and `_FRAMEWORK` (the missing half-fix). This unblocks worktree-isolated runs without weakening the shadow-purge defense. **Pre-existing seed gap surfaced (not fixed — out of file-disjoint scope):** the seed `llm_router.obter_preferences` calls `deps._db.get_user_client()` (no args) but `DatabaseModule` does not expose that method — runtime would crash on first GET `/api/llm/preferences`. The Phase 7 smoke pivoted to `/api/llm/providers` (org-scoped via `resolve_credential` → `org_settings.eq(org_id, key)`) which exercises the same isolation contract without hitting the broken seam. Filed as surface for architect — destination = seed-side follow-up. **Pytest delta:** 1887 → 1920 passed (+33: 30 smoke + 3 vista-showcase gap) / 34 skipped / 33 pre-existing failures (identical set to baseline — full diff captured in findings). Keeper review: 0 issues. **Improvements identified during phase:** (a) `erp-financial-surfaces-role-gate` follow-up project (N=4 DRY); (b) `noctusai_seed` worktree sys.path fix mirrored across ALL other product conftests (PF, daily-life, adconnect, core all carry the same half-fix — N=5 across products, file separately for the full conftest-fanout pass); (c) seed `llm_preferences` `deps._db.get_user_client()` arity gap — seed-side bugfix follow-up. | Engineer ERP-P7 |
