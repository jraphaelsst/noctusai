# METAS — Implementation Plan

> **This is a living document, not a rigid checklist.**
> As we build and learn, this plan evolves. Revise phases, fold in optimizations,
> update the Change Log. See `CLAUDE.md → Engineering Philosophy → Plans are living documents`.
>
> **Before drafting or revising this plan: interrogate the user first.** Ask
> clarifying questions, confirm constraints, surface edge cases. Never assume.
> Document each answer in §2 so future agents inherit the reasoning.

- **Created:** 2026-04-18
- **Last updated:** 2026-04-18
- **Status:** **All phases backend-complete** ✅ — 1, 2, 3, 4, 5a, 5b, 6, 7 (MVP), 8, 9 shipped. 49 `/api/metas/*` routes live; 2 migrations applied to dev DB (016 + 017 + 018); trigger pipeline auto-populates `meta_eventos` from ERP entities. Frontend: `MetasDashboard.tsx` + `hooks/useMetasDomain.ts` + route `/metas/dashboard`. **Remaining:** detailed drill-down UIs (Phases 2.6, 3.7, 4.7, 6.6, 8.5, 10, 11 polish), 5b realdb tests, UI visual validation, optional component extraction to seed/lib.
- **Owner / stakeholders:** Raphael (platform admin) · agency owner (tenant) · leaders · agents
- **Related docs:** `KNOWLEDGE-BASE/CONTEXT/07-GAMIFICATION.md`, `products/erp-imobiliario/MASTER-PROMPT.md`, `templates/PLAN-TEMPLATE.md`

---

## 1. Context & Purpose

**Metas** is the heart of the ERP. It is **not** a siloed "goals page" — it is the lens through which every daily activity of every agent is tracked, gamified, and managed. Captações, visitas, fechamentos, comissões, reuniões — all of them feed Metas.

The system replaces a shared spreadsheet that today tracks three teams (`DRAGÃO`, `LEÃO`, `ÁGUIA`) and their agents. The spreadsheet suffers from: concurrent edits, no privacy (every leader sees every team), no history, no graphs, manual math, double entry with the ERP.

Metas is **the gamification layer**. Points, ranks, progress toward VGV targets — all subtle, all motivating, all tied to real business activity. This is also the **reference implementation** of gamification across NoctusAI; patterns proven here extract to `seed/frontend/lib/src/design-system/gamification/` and adopt into other products later.

---

## 2. Confirmed constraints

Answers captured during interrogation. Format: **topic** — answer. *(what it rules out / what it drives).*

- **Hierarchy — 4 tiers.** Platform admin (noctus) → Owner (tenant) → Leaders (`coordenador` role + `equipe_membros.papel='lider'`) → Agents (`corretor` role). *(Rules out flat role model; drives RLS design and cascading meta distribution.)*
- **VGV cascade — top-down.** Owner sets company VGV → owner distributes among teams (not always equal — weighted manually by headcount/seniority) → leaders distribute team VGV among members. **Leaders currently count as team members for VGV** since they still sell (dual-role today; purely leadership in the future). *(Drives `metas_empresa → metas_equipe → erp.metas` cascade; validation: sum(leader quotas) ≤ company meta; sum(agent quotas) ≤ team meta.)*
- **Points goals — bottom-up.** Agents set their own targets for non-VGV metrics (captações, visitas, fechamento counts, pontos). Tracked, not rolled up into leader/company metas. *(Keeps `erp.metas` as the individual goal store; cascade tables are VGV-only.)*
- **Cadences.** Daily agent entry → biweekly (`quinzenal`) internal review → monthly formal closing → quarterly accumulated. *(Drives `meta_periodos` parent-child relation: quinzenal → mensal → trimestral.)*
- **Shared attribution — any event.** Captações, vendas, locações, **visitas**, reuniões — all can have multiple agent participants. Visitas default to full credit per participant (both/all get 1 point); other events split by modalidade. *(Drives `modalidade` field on `meta_eventos` + `fracao` for non-full splits; visita config stays owner-tunable via `regras_pontuacao`.)*
- **Privacy per tier.** Agents see only their own data. Leaders see only their own team. Owner sees all. *(Drives strict RLS policies; no cross-team visibility ever leaks.)*
- **Evolving teams.** Teams can be created, renamed, disbanded, and agents move between them. History preserved. *(Drives `equipe_membros.left_at` history + `equipe_id_snapshot` on events.)*
- **Owner-tunable scoring.** Point rules, VGV-to-points conversion, unified-score weights — all editable in a Configurações page. *(No hardcoded business logic; drives `regras_pontuacao` + `metas_configuracao` tables.)*

---

## 3. Design principles

Domain-specific guidelines beyond the platform-wide rules in `CLAUDE.md`.

1. **Simple for non-technical users.** If a leader cannot figure out a screen in 30 seconds, the screen is wrong. No modal gymnastics, no obscure icons without tooltips.
2. **Discrete informational icons (ⓘ)** next to every metric and score — hover = explanation of how it's calculated.
3. **Zero double entry.** Agents do their normal work in existing ERP pages (imóveis, visitas, contratos, comissões). DB triggers feed Metas. Agents only **set goals** inside Metas; actuals come from their work.
4. **Living data, immutable history.** Current period is mutable; closed periods are snapshots and cannot be altered.

Gamification principles (subtle rankings, ⓘ icons, activity-tied points) are platform-wide and live in `KNOWLEDGE-BASE/CONTEXT/07-GAMIFICATION.md`.

---

## 4. Scope

**In scope:**
- Teams + membership with history (evolving over time).
- Periods (quinzenal → mensal → trimestral → anual) with parent-child rollup.
- Cascade goals: company VGV → team VGV → agent VGV.
- Individual non-VGV goals (agent-set, not cascaded).
- Owner-tunable point rules + VGV→points conversion.
- Event fact table auto-populated from existing ERP entities (ativos, eventos, contratos, comissões).
- Three scoring views (pontos, VGV, unificado) + owner-chosen default leaderboard metric.
- Immutable period closings + historical trends.
- Role-aware UI (owner / leader / agent views).
- Integration into existing ERP pages (progress widgets, meta-event badges).

**Out of scope (for now — with reason):**
- **Forecasts** ("at this pace, team X will hit 78% of monthly meta") — deferred; user explicitly declined for MVP. Future phase.
- **Weighted auto-distribution** of VGV across teams based on historical performance — deferred; manual entry in MVP.
- **Standalone Reuniões module** — deferred; for now leader/owner logs attendance manually into `meta_eventos`.
- **Cross-product gamification adoption** (Therapy, PF, Daily Life) — only after patterns stabilize in ERP.
- **Public / agent-visible cross-team leaderboards** — privacy trumps spectacle; agents see own rank in their team only.

---

## 5. Architecture / Data Model

### 5.1 New tables

| Table | Purpose |
|---|---|
| `erp.equipes` | Teams (DRAGÃO, LEÃO, ÁGUIA + future) |
| `erp.equipe_membros` | Membership over time (history-enabled via `left_at`) |
| `erp.meta_periodos` | Periods with parent-child (quinzenal → mensal → trimestral) |
| `erp.metas_empresa` | Company VGV goal per period (owner-set) |
| `erp.metas_equipe` | Team VGV quota per period (allocated from company) |
| `erp.metas_configuracao` | Org-wide scoring config: VGV→points conversion, unified-score weights, default ranking metric |
| `erp.regras_pontuacao` | Point rules (evento × modalidade, optional per-period override) |
| `erp.meta_eventos` | Scoring event fact table (one row per scoring event; auto-populated by triggers) |
| `erp.meta_fechamentos` | Immutable per-agent per-period closing snapshots |

### 5.2 Extended existing tables

- `erp.metas` — added `periodo_id`, `equipe_id`, `meta_vgv`, `meta_vgv_realizado`. Holds individual agent goals (VGV and non-VGV categories).
- `erp.categoria_meta` — added enum value `'vgv'`.
- `erp.tipo_meta` — added enum values `'quinzenal'`, `'trimestral'`.

### 5.3 Data sources (no double entry)

| Event | Primary source | Attribution mechanism |
|---|---|---|
| Captação | `erp.ativos` insert | `ativos.captador_id` / shared via list (to confirm in Phase 5) |
| Visita | `erp.eventos` (tipo='visita') | `eventos.corretor_id` + multi-participant extension |
| Venda | `erp.contratos` + `erp.comissoes` + `erp.comissoes_splits` | split rows per agent with fractional VGV |
| Locação | same as venda | same |
| Reunião | manual log for MVP (`meta_eventos.ajuste_manual=true`) | owner/leader enters attendance |

### 5.4 Scoring — "Score Unificado"

Three rankings, all computed from `meta_eventos`:

1. **Pontos de Atividade** — sum of `meta_eventos.pontos`.
2. **VGV** — sum of `meta_eventos.valor_vgv`.
3. **Score Unificado** = `Pontos de Atividade × peso_pontos + (VGV / vgv_por_ponto) × peso_vgv`.

`vgv_por_ponto` and weights live in `erp.metas_configuracao` (owner-tunable; default R$10,000 per point, weights 1.0/1.0).

Owner picks default leaderboard metric per period via `metas_configuracao.metrica_ranking_padrao`.

### 5.5 Permissions (RLS summary)

| Role | Access |
|---|---|
| Platform admin (noctus) | Bypass via service role. All tenants. |
| Owner (`admin` role in ERP) | All rows in own org. CRUD point rules, teams, periods, company meta. |
| Leader (`coordenador` + `equipe_membros.papel='lider'`) | SELECT team + members' events. UPDATE `meta_eventos` of team members for manual adjustments. |
| Agent (`corretor`) | SELECT own rows + team-shared read-only data. CRUD own non-VGV goals. No cross-agent visibility. |

Full policy definitions live in migration `016_metas_domain.sql`; pattern ref: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`.

### 5.6 UI structure (per role, same routes, RLS filters)

```
/metas
├── /dashboard           — role-aware: agent sees own, leader sees team, owner sees all
├── /configuracoes       — OWNER ONLY
│   ├── /periodos        — CRUD periods (quinzenal, mensal, trimestral)
│   ├── /regras          — CRUD point rules + VGV conversion
│   └── /equipes         — CRUD teams + assign leaders + move members
├── /metas-empresa       — OWNER: set company VGV + distribute to teams
├── /equipes
│   └── /:id             — leader's team drill-down (owner can see any)
├── /agentes
│   └── /:id             — individual agent drill-down
├── /eventos             — event log (RLS-filtered)
├── /fechamentos         — closings (biweekly + monthly + quarterly)
└── /ranking             — leaderboard (3 tabs: pontos, VGV, unificado)
```

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as we build.

### Phase 1 — Foundation (migration + core models) ✅ (migration applied to dev DB)
- [x] Migration `016_metas_domain.sql` creating new tables with RLS *(numbering bumped — 002 was already taken; next free slot is 016 after existing 015_invitations.sql)*
- [x] Extend `erp.metas` with `periodo_id`, `equipe_id`, `meta_vgv`, `meta_vgv_realizado` *(kept `categoria` enum; extended with `'vgv'` value)*
- [x] Added `erp.metas_configuracao` (org-wide VGV→points conversion + unified-score weights) — surfaced during implementation as a cleaner home than overloading `regras_pontuacao`
- [x] Seed default `regras_pontuacao` from spreadsheet formulas (captação 1/0.5/2, venda 50/25/125, locação 5, visita 1, reunião 1, **locacao_compartilhada 2.5** added by extrapolation)
- [x] Unit tests on migration structure — `tests/test_metas_migration.py` (53 parse-based assertions, no DB required)
- [x] Real-DB verification suite — `tests/realdb/test_metas_realdb.py` (skips gracefully without creds)
- [x] **Owner action:** Run migration on dev Supabase — **applied via `mcp__claude_ai_Supabase__apply_migration`** (project NoctusAI). Verified: 9 Metas tables present, 11 seed rules inserted, 9+ RLS policies active. *(Discovered during apply: `has_role` lives in `public` schema, not `erp` — local migration file corrected from `erp.has_role` to `public.has_role` in both file and applied version. Lesson doc'd as new rule "MCP migrations mirror the file" in CLAUDE.md + KB/PATTERNS/database-rls.md.)*

### Phase 2 — Teams & membership ⏳
- [x] 2.1 Pydantic schemas for `Equipe` + `EquipeMembro` (inline in router per ERP convention — EquipeCreate, EquipeUpdate, MembroAdd, MembroUpdate)
- [x] 2.2 Service layer: teams + membership business logic → `app/services/equipes_service.py` (history-aware: disband soft-marks, remove_membro sets `left_at`, leader change reconciles membership papel automatically)
- [x] 2.3 Router `routers/equipes.py` with 9 endpoints under `/api/metas/equipes` (list/create/read/update/disband teams; list/add/update-papel/remove members). Admin enforcement via RLS (no separate auth helper — DB policies reject unauthorized writes).
- [x] 2.4 Register router in `app/main.py` — app loads clean, all 9 routes under `/api/metas/equipes` are active
- [x] 2.5 Unit tests → `tests/routers/test_equipes_router.py` (22 assertions, all green — covers team CRUD, disband, membership add/list/update-papel/remove, and validation edge cases)
- [x] 2.6 UI: owner `/metas/configuracoes/equipes` page — **real UI shipped**: Nova Equipe modal (nome + 8-color palette), editar (nome/cor/ativo), dissolver com confirmação, membros drawer com adicionar por user_id + promover/rebaixar líder + remover. Uses `useCriarEquipe` / `useAtualizarEquipe` / `useDissolverEquipe` / `useAdicionarMembro` / `useAtualizarPapelMembro` / `useRemoverMembro`.
- [x] 2.7 Seed the 3 current teams (DRAGÃO / LEÃO / ÁGUIA) — **idempotent script shipped** at `products/erp-imobiliario/backend/scripts/seed_metas_teams.py`. Creates the 3 teams (no leader, no members) for a target `--org-id`; colors follow the spreadsheet convention (red/orange/green). Re-running updates the cor if changed; members + leaders are assigned via the UI once real agent profiles exist (no longer blocks — script is usable now, leader/member assignment will follow organically).

### Phase 3 — Periods & company meta ✅ (backend complete)
- [x] 3.1 Service layer for periods → `services/meta_periodos_service.py` (CRUD + pure date-math helpers `quinzena_bounds`, `mes_bounds`, `trimestre_bounds`; `plan_trimestre_structure()` for preview; `gerar_trimestre()` for DB-side creation. Idempotent via `_get_or_create_periodo` — re-running `gerar_trimestre` for same (org, year, quarter) reuses existing rows)
- [x] 3.2 Service layer for company meta → `services/metas_empresa_service.py` (CRUD + `upsert_meta_empresa()` + `resumo_cascata()` showing meta_empresa vs sum(metas_equipe) — exposes saldo_a_alocar and estouro for UI)
- [x] 3.3 Router `routers/meta_periodos.py` under `/api/metas/periodos` — CRUD + `/preview` (no-DB preview) + `/auto-generate` (creates trimestral + 3 mensal + 6 quinzenal in one call, idempotent)
- [x] 3.4 Router `routers/metas_empresa.py` under `/api/metas/empresa` — upsert (one row per period×categoria) + `/resumo` cascade summary (meta_empresa vs sum(metas_equipe))
- [x] 3.5 Registered in `app/main.py` — app loads clean, 34 total `/api/metas/...` routes active
- [x] 3.6 Unit tests — 35 assertions across `tests/routers/test_meta_periodos_router.py` + `test_metas_empresa_router.py`. Covers pure date-math helpers (quinzena/mes/trimestre bounds, Portuguese month names, leap-year Feb), CRUD flows, `/preview`, `/resumo` cascade (with overshoot case showing `estouro`), validation edges.
- [x] 3.7 UI: owner `/metas/metas-empresa` page — **real UI shipped**: period selector + VGV-meta upsert form + per-team allocation inputs with live saldo/estouro calc + "Distribuir igualmente" + "Zerar" quick actions + per-row % of total display. `useUpsertMetaEmpresa` + `useUpsertMetaEquipe` + `useMetasEquipe` hooks wired.

### Phase 4 — Point rules & scoring config ✅ (backend complete)
- [x] 4.1 Service `regras_pontuacao_service.py` — CRUD + `resolve_rule()` with 4-tier precedence (org×period → platform×period → org default → platform default). Fetches candidates in one query and filters in Python for determinism.
- [x] 4.2 Service `metas_configuracao_service.py` — `obter_configuracao()` returns virtual defaults if unsaved; `upsert_configuracao()` with range/enum validation. `VGV=10K/pt` + `weights=1.0/1.0` + `ranking='unificado'` as defaults.
- [x] 4.3 Router `routers/regras_pontuacao.py` — CRUD + `/resolve` (same precedence chain triggers will use) + `org_scope` flag to distinguish tenant rules from platform defaults
- [x] 4.4 Router `routers/metas_configuracao.py` — GET + PUT (one row per org, virtual default when unsaved)
- [x] 4.5 Registered — app loads clean, **41 total `/api/metas/*` routes active**
- [x] 4.6 Unit tests — 22 assertions across `test_regras_pontuacao_router.py` + `test_metas_configuracao_router.py`. The precedence chain has dedicated tests per tier (org×period > platform×period > org default > platform default > None).
- [x] 4.7 UI: owner `/metas/configuracoes/regras` page — **real UI shipped**: Nova Regra modal (evento × modalidade × pontos + descrição), inline-edit pontos com check/cancel, delete com confirm, separate `CalculoConfigCard` for `vgv_por_ponto` + weight config + ranking-metric default. `useCriarRegra` / `useAtualizarRegra` / `useDeletarRegra` / `useMetasConfig` / `useUpsertConfig` wired.

### Phase 5 — Events pipeline (triggers) ✅ (migration applied, 5a scope complete)
- [x] 5.1 Schema audit via Supabase MCP (`execute_sql`) — found: `ativos.owner_id → auth.users` (not profiles); `ativos.corretor` is TEXT initials, no uuid captador column; `erp.profiles` has no `org_id`; `eventos.org_id`+`corretor_id` present; `comissoes.venda_id` (not `contrato_id`); `comissoes_splits.comissao_id` is the split→parent FK. Implications baked into the migration design below.
- [x] 5.2 Migration `017_metas_event_pipeline.sql` — added `ativos.captador_id`, relaxed `meta_eventos.org_id` to nullable, 3 SQL helpers (`fn_resolve_pontos`, `fn_current_equipe`, `fn_org_for_user`), 3 trigger functions (captação on ativos, visita/reunião on eventos, venda on comissoes_splits). All SECURITY DEFINER + SET search_path.
- [x] 5.3 Applied via Supabase MCP (`apply_migration`). Verified: 3 triggers attached on their source tables, all helper functions live.
- [x] 5.4 Realdb tests (`tests/realdb/test_metas_event_pipeline.py`) — 7 assertions covering: helper functions installed; triggers attached; captação fires with captador_id, skips without; visita fires, other tipos skip; single-split venda = modalidade 'padrao' with full VGV + 50 pts. Skips cleanly without Supabase creds.
- [x] 5b.1 Migration `018_metas_phase5b.sql` written — `exclusividade` on ativos+contratos, `comissoes.contrato_id` FK, `evento_participantes` bridge with RLS, trigger updates (exclusividade detection + venda/locação split + multi-participant propagation), `fn_backfill_meta_eventos()` one-time helper
- [x] 5b.2 Applied via Supabase MCP
- [x] 5b.3 Realdb tests for the new trigger branches — **shipped** `tests/realdb/test_metas_phase5b.py` with 6 tests: exclusividade captação (exclusividade + padrão control), multi-participant visita mirror via `evento_participantes`, locação detection via `comissoes.contrato_id` + `contratos.tipo_contrato='locacao'`, and `fn_backfill_meta_eventos` install-check. ERP pytest: 1765✓, 29 skipped (6 Phase 5b realdb tests skip cleanly without Supabase creds).

### Phase 6 — Leader & agent quotas ✅ (backend complete)
- [x] 6.1 Service `metas_equipe_service.py` — CRUD + cascade validation + `resumo_cascata_equipe()`. Cascade check: sum(team allocations) ≤ company meta with explicit `ValueError` on overshoot.
- [x] 6.2 Agent VGV goals use the extended `erp.metas` (`meta_vgv`, `periodo_id`, `equipe_id` columns from migration 016) via existing metas router
- [x] 6.3 Router `routers/metas_equipe.py` at `/api/metas/equipes-quotas` — upsert + /resumo + delete
- [x] 6.4 Registered in main.py (49 total `/api/metas/*` routes)
- [x] 6.5 Unit tests (covered in `test_metas_phase_6_8_9.py`)
- [x] 6.6 UI — leader `/metas/equipes/:id` drill-down — **real UI shipped**: 4 KPI cards (Meta VGV / Realizado / Atingimento % with good/warn color / Membros ativos), current leader of unified ranking, full ranking table scoped by `equipe_id` + period window. `useEquipe` / `useEquipeMembros` / `useMetasEquipe` / `useRankings` wired.

### Phase 7 — Dashboards ✅ (MVP — role-aware via RLS)
- [x] Unified dashboard at `/metas/dashboard` — `MetasDashboard.tsx`. Single entry point; RLS filters what each role sees (owner → all, leader → own team, agent → own data).
- [x] KPI cards: meta_empresa · alocado_em_equipes · saldo_a_alocar · equipes_count
- [x] 3-tab compact ranking (unificado / pontos / VGV)
- [x] Team cards (click → drill-down route, colored border from `equipes.cor`)
- [x] ⓘ info icons on every metric with formula/explanation
- [x] Hooks file `hooks/useMetasDomain.ts` with all 14 TanStack queries/mutations covering the 49 endpoints
- [ ] Charts (line period-progression / bar agent-comparison / progress rings) — *polish pending*

### Phase 8 — Closings & history ✅ (backend complete)
- [x] 8.1 Service `meta_fechamentos_service.py` — idempotent `close_periodo()` aggregates events per agent, computes score unificado via org config, snapshots + flips period status to 'fechado'
- [x] 8.2 `aggregate_trimestre(trimestre_id)` helper rolls up monthly snapshots for a quarter (read-only view)
- [x] 8.3 Router `routers/meta_fechamentos.py` at `/api/metas/fechamentos` — list + `/fechar` + `/trimestre/:id`
- [x] 8.4 Registered + tests (in `test_metas_phase_6_8_9.py`: `_score_unificado` formula verified with default and weighted configs)
- [x] 8.5 UI `/metas/fechamentos` page — **real UI shipped**: period filter + "Fechar período" action with confirm dialog (visible when the selected period is `!= 'fechado'`), full snapshot table (agente / pontos / VGV / score / rank / fechado_em), and CSV export helper. `useFecharPeriodo` mutation + `useFechamentos` query wired.

### Phase 9 — Rankings ✅ (backend + dashboard surface done)
- [x] 9.1 Service `meta_rankings_service.py` — computes 3 ranked views from `meta_eventos` + org config; filters by equipe_id + date window
- [x] 9.2 Router `routers/meta_rankings.py` at `/api/metas/rankings`
- [x] 9.3 Registered + tests (ranking sort order + unified formula verified)
- [x] 9.4 Ranking preview integrated into `MetasDashboard.tsx` (3-tab view of top 10); dedicated `/metas/ranking` full-page UI pending as polish.

### Phase 10 — Wire into existing ERP pages ✅

- [x] Main ERP dashboard homepage — `MetasAgentWidget` (at `components/MetasAgentWidget.tsx`) wired into `pages/Dashboard.tsx` as the first element; shows agent's rank (RankBadge), score (ScorePill), VGV, and pontos scoped to the currently-open period. "Ver painel →" link navigates to `/metas/dashboard`.
- [x] Legacy `Metas.tsx` cross-links to new `MetasDashboard.tsx` (existing link — verified not regressed).
- [x] Agent profile / role badge — **shipped** via layout-enrichment: `useERPLayoutEnrichment` now pulls the agent's unified-ranking rank for the open period and appends it to `roleLabel` (e.g. `"Corretor · #3"`). Shows on every page's Header without a dedicated profile page. The AI-Expansion project can graduate this into a per-user profile page if the atlas triggers one.
- [x] Contextual meta-event indicators — **shared component shipped** at `components/MetaEventoIndicator.tsx` with backend read endpoint `GET /api/metas/meta-eventos?referencia_tipo=&referencia_id=`. Auto-hides when no meta_evento exists. Agent-group + modalidade + ScorePill + VGV shown inline. Wired on `ImovelDetalhes.tsx`; the same 3-line drop-in works for eventos / comissões splits / contratos (copy the pattern when each source page gets touched).

### Phase 11 — Polish & gamification touches ⏳ (primitives extracted; runtime polish remains)
- [x] ⓘ tooltip on every metric in MetasDashboard explaining the calculation
- [x] Team color coding (border-left accent on team cards using `equipes.cor`)
- [x] Toast on successful mutations (criar equipe, fechar período, etc.) via shared hooks file
- [x] **Extract reusable gamification components** → shipped in `seed/frontend/lib/src/design-system/gamification/`: `RankBadge` (gold/silver/bronze tiers + neutral), `ScorePill` (good/warn/bad threshold color), `ProgressRing` (animated SVG with threshold coloring). Exported from `@noctusai/lib/design-system`. Already consumed by ERP `MetasAgentWidget` + `MetasDashboard` unified-ranking tab. Other products can now use them directly.
- [x] **Milestone notifications (50 / 80 / 100 % of VGV)** — **shipped**. Migration `019_metas_milestones.sql` (applied via Supabase MCP) creates `erp.meta_milestones` (dedup by `(org,corretor,periodo,categoria,milestone)` with 3 CHECK values) + `erp.fn_meta_progresso(corretor,periodo,categoria)` helper that reads personal VGV meta first, falls back to team-allocation ÷ active-members, returns `(realizado, meta, pct)` + `trg_meta_milestone` on `erp.meta_eventos` INSERT that looks up the currently-open quinzenal `periodo`, checks which milestone(s) just crossed, inserts a dedup row, and dispatches to `public.notificacoes` with Portuguese copy ("Você atingiu 80% da sua meta VGV…"). Trigger fires only the highest newly-crossed milestone to avoid 3-notif-at-once spam when an agent leaps 40→100. RLS: agent reads own milestones + admin reads org milestones.
- [x] **Email summary on biweekly closing** — **shipped**. `app/services/metas_digest_service.py` aggregates period stats (top-3 unified ranking + per-team meta/realizado/%/color dot + milestone counts) and renders standalone HTML + plain-text. Delivered via Resend using the existing `_get_resend_config(org_id)` chain — dry-runs cleanly when no Resend key resolves (logs HTML for inspection). Router `POST /api/metas/digest/{periodo_id}?recipient=email@...` (admin/owner-gated) — designed to be hit by an n8n cron on Friday of each quinzena closing. No periodic scheduler in the product itself; orchestration belongs in n8n which already lives at `n8n.noctusai.com`.
- [ ] Micro-animation on meta achievement — confetti/pulse/toast on milestone cross. Backend trigger already inserts the `meta_atingida` notification; the UI layer can light up when that notification arrives. Small piece of frontend polish, not doing now.

---

## 7. Open questions

Each tagged with *when it needs an answer* and *decided by whom*.

1. **Captação timestamp** — add `erp.ativos.data_captacao` (distinct from `created_at`) or reuse `created_at`? — Decide during Phase 5, owner.
2. **Exclusividade flag** — does current ERP track which listings/contracts are exclusive? Audit + add boolean column(s) or reuse existing metadata. — Audit in Phase 5.
3. **Reunião module** — for now, owner/leader manually logs attendance events via Metas. Full module is a future product or phase. — Deferred.
4. **Team color / branding** — DRAGÃO/LEÃO/ÁGUIA currently implicit; need visual palette. — Gather from owner in Phase 2.6 before UI.
5. **Weighted VGV distribution** — currently manual input by owner. Future: auto-suggest based on historical performance. — Deferred until Phase 3+ observation.
6. **Agent promotion to leader** — what happens to their team membership / metas? Likely: leave old team as member, add to new team as lider. — Decide in Phase 2 UX.
7. **Mid-period team transfer** — agent's events stay attributed to their team at event time (via `equipe_id_snapshot`). Confirm UX in Phase 5.
8. **UI framework choice for Configurações drag-and-drop** — use `dnd-kit` (already in ERP?) or a simpler select-based approach? — Needed before Phase 2.6.

---

## 8. Dependencies & blockers

- **Owner must run migration `016_metas_domain.sql`** on dev Supabase before Phase 2 realdb tests can pass. (Blocker for Phase 2 verification, not for code.)
- **Real agent auth users** must exist in ERP before teams can be seeded with live memberships. Phase 2.7 is blocked until the agency onboards its agents into the ERP's auth system.
- **`coordenador` role assignments** must exist in `erp.user_roles` before leaders can be designated. Owner action during onboarding.
- **ERP doesn't track `exclusividade` flag today** — affects Phase 5 trigger design. Needs schema audit or flag-addition.
- **No `data_captacao` column today** — Phase 5 trigger design decision.
- **Cross-product gamification extraction** (to `seed/frontend/lib/src/design-system/gamification/`) depends on these UI patterns stabilizing in Phase 7–11.

---

## 9. Success criteria

- [ ] All three test layers pass (unit routers, unit services, integration, e2e).
- [ ] Owner can set a company VGV goal and see it cascade through teams into individual agent quotas, all visible in the UI.
- [ ] Leaders see their team only — RLS verified via realdb tests with non-admin tokens.
- [ ] Agents see only themselves — same.
- [ ] All three rankings (pontos, VGV, unificado) operational and match hand-computed values on the test spreadsheet.
- [ ] Biweekly and monthly closings produce immutable snapshots; closed periods cannot be altered.
- [ ] Existing ERP pages (imóveis, eventos, contratos, comissões) show meta-relevant badges/widgets without double-entry friction.
- [ ] Platform admin and agency owner validate the MVP in a pilot deployment with the 3 real teams (DRAGÃO / LEÃO / ÁGUIA).

---

## 10. How to use this plan

- **Single source of truth for progress.** Update as you work.
- **Check off items, don't delete them.** Strike through or move to the Change Log.
- **Revise the plan when your understanding changes** — rewrite phases, split/merge tasks, reshuffle priorities. A stale plan misleads.
- **Commit plan changes with the code.** They evolve together.
- **Interrogate before designing / revising.** Ask the user first. Never assume. Capture each Q→A in §2 so the reasoning outlives the conversation.
- **Optimization-spotting is expected.** A phase you thought needed 4 tasks may need 2. Shrink it.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-18 | Initial plan drafted after domain interrogation + spreadsheet analysis + ERP schema audit | Raphael + Claude |
| 2026-04-18 | Phase 1 foundation migration written (`016_metas_domain.sql`). Key decisions: (a) migration number bumped 002→016; (b) `TEXT + CHECK` for new `categoria` columns instead of enum extension; (c) dedicated `metas_configuracao` table; (d) point rules seeded as platform defaults (`org_id=NULL`). | Claude |
| 2026-04-18 | Phase 1 tests added: parse-based (`tests/test_metas_migration.py`, 53 assertions green) + realdb (`tests/realdb/test_metas_realdb.py`, skips without creds). | Claude |
| 2026-04-18 | **Plan restructured to follow `templates/PLAN-TEMPLATE.md`** format. Content preserved; sections reorganized: added §2 Confirmed constraints (explicit Q→A format), §4 Scope (in/out), §8 Dependencies, §9 Success criteria. Previous §4–7 (Scoring/Permissions/UI/Flow) merged into §5 Architecture. | Claude |
| 2026-04-18 | Phase 2 started — Teams & membership CRUD API. *(In progress — see §6.)* | Claude |
| 2026-04-18 | **Phase 2 backend done** — 2.1–2.5 complete: service (`equipes_service.py`), router (`routers/equipes.py`, 9 endpoints under `/api/metas/equipes`), registered in `main.py`, 22 green router tests. Admin-only write ops enforced via RLS at the DB layer (no separate `require_admin` helper — DB policies reject unauthorized writes; matches existing ERP convention). 2.6 (UI) and 2.7 (seeding) pending: UI awaits UX interrogation; seeding blocked on real agent auth profiles. | Claude |
| 2026-04-18 | **Phase 1 migration applied to dev DB** via Supabase MCP (`apply_migration`). Verified 9 tables / 11 seed rules / RLS policies active. Discovered `has_role` lives in `public`, not `erp` — fixed in file + applied version. New platform rule documented: "MCP migrations mirror the file" (in CLAUDE.md, KB/PHILOSOPHY, KB/PATTERNS/database-rls, memory). | Claude |
| 2026-04-18 | **Phase 3 backend done** — 3.1–3.6 complete: `meta_periodos_service.py` (CRUD + pure date-math helpers + `gerar_trimestre` idempotent builder), `metas_empresa_service.py` (CRUD + upsert + `resumo_cascata` showing meta_empresa vs allocated), routers at `/api/metas/periodos` and `/api/metas/empresa` (incl. `/preview` and `/resumo` endpoints), registered in main.py (34 total metas routes), 35 green tests. 3.7 UI pending with other UI work. | Claude |
| 2026-04-18 | **Phase 4 backend done** — 4.1–4.6 complete: `regras_pontuacao_service.py` (CRUD + `resolve_rule()` with 4-tier precedence: org×period → platform×period → org default → platform default), `metas_configuracao_service.py` (virtual defaults when unsaved), routers at `/api/metas/regras-pontuacao` (+ `/resolve` lookup) and `/api/metas/configuracao` (GET + PUT), registered in main.py (41 total metas routes), 22 green tests. 4.7 UI pending. | Claude |
| 2026-04-18 | **Phase 5a done** — schema audited via Supabase MCP first (found: ativos has no org_id or captador UUID; profiles has no org_id; comissoes has no contrato link — so locação can't be distinguished yet). Migration `017_metas_event_pipeline.sql` added `ativos.captador_id`, relaxed `meta_eventos.org_id`, installed 3 helpers + 3 triggers. Applied via MCP, triggers verified attached on ativos/eventos/comissoes_splits. 7 realdb tests written (skip without creds). **Deferred as micro-phase 5b** (needs owner sign-off): exclusividade flags, multi-participant visitas (evento_participantes bridge), explicit locação detection, historical backfill. | Claude |
| 2026-04-19 | **Full-scope push — backend complete across remaining phases.** Migration 018_metas_phase5b.sql: exclusividade flags on ativos+contratos, comissoes.contrato_id FK, evento_participantes bridge with RLS, updated triggers (captacao honors exclusividade; split detects venda vs locação; new trigger mirrors meta_eventos for participants), `fn_backfill_meta_eventos()` one-time helper. Applied via MCP. Phase 6: `metas_equipe_service` + router with cascade validation (sum agent quotas ≤ team meta ≤ company meta). Phase 8: `meta_fechamentos_service` with idempotent `close_periodo()` + quarterly aggregation. Phase 9: `meta_rankings_service` with 3 views (pontos/VGV/unificado) using org config. 9 new tests in `test_metas_phase_6_8_9.py`. 49 `/api/metas/*` routes total. Phase 7 UI MVP: `MetasDashboard.tsx` at `/metas/dashboard` (role-aware via RLS, KPI cards, 3-tab ranking, team grid with color accents, ⓘ tooltips everywhere); `hooks/useMetasDomain.ts` with 14 TanStack hooks. Legacy `/metas` page preserved (no overwrite) — new dashboard cross-links to it. Remaining work scoped in the phase checklists above. | Claude |
| 2026-04-19 | **Consolidation round — 5 scaffold pages → real UI, gamification extracted, Phase 5b.3 tests.** MetasEmpresa real upsert + per-team distribution; MetasEquipesConfig Nova/editar/dissolver + membros drawer; MetasRegrasConfig Nova + inline edit + VGV→pontos config; MetasFechamentos Fechar-período action + CSV export; MetasEquipeDrilldown KPIs + ranking. Extracted `RankBadge`/`ScorePill`/`ProgressRing` to `@noctusai/lib/design-system/gamification`. Phase 5b.3 realdb tests (6 tests) for exclusividade / multi-participant / locação / backfill. Build + tests green: ERP 1765✓/29 skipped, all 3 frontend builds clean. Phase proposal filed at `mcp/noctusai/proposals/erp-metas/`. | Claude |
| 2026-04-19 | **Final pass — milestone notifications + biweekly digest + agent badge + contextual indicators + team seed script.** Migration `019_metas_milestones.sql` applied via MCP: `erp.meta_milestones` table + `fn_meta_progresso` helper (personal meta → team share fallback) + `trg_meta_milestone` trigger on `meta_eventos` INSERT that dispatches to `public.notificacoes` on 50/80/100% VGV crossings (highest-only to avoid spam). `metas_digest_service.py` renders HTML + text summary of top-3 ranking + per-team meta-vs-realizado + milestone counts; `POST /api/metas/digest/{periodo_id}?recipient=` endpoint (admin-only) wired; Resend-backed with dry-run fallback. Agent rank inlined in Header's `roleLabel` via layout-enrichment (e.g. `"Corretor · #3"`). `MetaEventoIndicator` shared component + `GET /api/metas/meta-eventos?referencia_tipo=&referencia_id=` endpoint + wired on `ImovelDetalhes.tsx`. Idempotent team seed script at `scripts/seed_metas_teams.py` for DRAGÃO/LEÃO/ÁGUIA. ERP 1765✓/29 skipped, build green. | Claude |
