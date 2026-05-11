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
- **Last updated:** 2026-05-11 (Phase 0 ✅)
- **Status:** ⏳ **Phase 0 ✅ — awaiting "continue" before Phase 1.** Discovery
  pass complete; §5.4 populated; §6 phases rewritten from concrete gap data;
  §7 design batch surfaced. Per the project's pause-after-each-phase cadence,
  awaiting user signal before Phase 1 dispatch.
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

### Phase 1 — Seed-side absorption batch (verify-seed-ships-it on PF retro §e rows)

Mirrors PF Phase 1 shape. For each row in PF retro §e, run the verify-seed-ships-it test (read seed's `__init__.py` exports + concrete adapter), then:
- If seed ships it → adopt across ERP backend.
- If seed has Protocol + Fake only → defer with destination (file follow-up project / `accept-with-rationale` entry).
- If seed is fully absent → file follow-up project, ship against Fake.

- [ ] **`make_get_current_user_org` adoption / defer decision.**
- [ ] **AI plumbing wrappers (`safe_persist_indicator`, `require_credential_or_422`, `check_openai_configured`) adoption / defer decision.**
- [ ] **`noctusai_lib.domain.metas` consumer-side adoption** — retire local `Goal/Period/Progress` shapes in `services/metas_*_service.py`; switch to seed primitives.
- [ ] **`make_require_role` adoption** for `vista_showcase.require_admin` + `metas_digest` inline check (Pattern F).
- [ ] **Status-code-assertion calibration** — run `noctus.dev.scan_block_patterns mode=status_assertion` over ERP test corpus; produce inventory; either fix inline OR pin baseline-no-regress.
- [ ] **DELETE pre-check uniformity audit** — confirm every `.delete().execute()` site uses `noctusai_lib.api.crud_safety.delete_or_404`; backfill any that don't (PF retro §e row 6 — N=9 backlog filed).
- [ ] **`vi.importActual` / `vi.hoisted` test patterns** — pre-document fix from PF retro §d for ERP frontend test brief.
- [ ] Phase-1 proposal filed via `noctus.dev.file_proposal`.

### Phase 2 — Admin Tier A: any known regressions

Phase 0 surfaced 0 explicit 404/405 regressions. Phase 2 may collapse into Phase 3 if user signal indicates no regressions worth a dedicated batch. **Skeleton kept in case Phase 1 surfaces fresh regressions during seed-absorption work.**

- [ ] Re-scan post-Phase-1 for any 4xx surfaces.
- [ ] If empty: collapse into Phase 3.

### Phase 3 — DTO normalization sweep (operational contract, NOT `response_model` rollout)

Per §5.4.6 — frontend `types/` is the operational DTO contract. Phase 3 ensures every list-endpoint maps raw DB rows to typed shapes BEFORE the HTTP boundary. `response_model=PydanticDTO` rollout DEFERRED to follow-up `erp-imobiliario-dto-contract` project (§7 Q-E).

- [ ] Audit every admin list endpoint for raw-DB-row leak.
- [ ] Mappers land in `app/services/<domain>_service.py`.
- [ ] Tests pin DTO shape at the router boundary.

### Phase 4 — Pre-existing scaffolding debt

- [ ] Refactor `useNegociacoes`, `useUserProfile`, `useUserRoles` from supabase.from() to backend routes (Pattern D-variant).
- [ ] `pages/Configuracoes.tsx` raw-fetch into core API → either hook-mediate via `noctusai_lib` cross-product helper OR catalog `accept-with-rationale`.
- [ ] `useAtualizarStatusMetas` orphan-hook resolution per §7 Q-NEW-DEL.
- [ ] Verify all DELETE sites use `delete_or_404` (Phase 1 fold-over if not done there).
- [ ] Audit Pattern G mixed shapes (`contratos/parcelas`) — accept or refactor.

### Phase 5 — Corretor (broker) portal wiring

Every `/admin/*` + corretor-tier surface — Atividades, Funil, Distribuição, Agenda, Vistorias-mobile (campo), Comissões, Marketing, BI.

- [ ] Per-page audit + wiring (sub-tasks land at phase kickoff once §5.4.3 per-hook map is densified — Phase 0 captured the headline; Phase 5 densifies the corretor-specific hooks).
- [ ] Tests + golden-path QA.

### Phase 6 — Portal-cliente + portal-externo wiring

- [ ] `portal_cliente.py` (9 endpoints) + `portal_externo.py` (8 endpoints) audit + wiring.
- [ ] LGPD flag for portal-externo public surfaces (no auth context).
- [ ] Tests + manual QA on public-link flow.

### Phase 7 — Standard-router mount smoke + admin-financials + vista-showcase

- [ ] **PF Phase 7 lesson §d.4 — 5-test standard-router smoke pattern** for `health`, `notificacoes`, `team`, `llm`, `ai_outputs`, `ai_feedback`.
- [ ] `vista_showcase` admin SSO gate audit + tests.
- [ ] Financeiro / DIMOB / Impostos / Banco wiring (these are the highest-LGPD-sensitivity surfaces).

### Phase 8 — End-to-end verification

- [ ] Full `pytest tests/` from ERP backend → green.
- [ ] `npx vite build` from ERP frontend → green.
- [ ] Manual browser QA per role tier (admin / coordenador / corretor / portal-cliente / portal-externo / public).
- [ ] `accept-with-rationale` catalog entries committed for any deferred items.
- [ ] PF-style lessons retro at `archive/projects/<YYYY-MM-DD>/<seq>-erp-wiring/erp-wiring-lessons.md`.

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
