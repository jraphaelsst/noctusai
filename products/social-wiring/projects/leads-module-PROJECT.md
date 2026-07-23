# Leads module — social-wiring · PROJECT

> **Status:** ✅ SHIPPED + LIVE IN PROD (2026-07-23) · **Owner:** tech-lead · **Started:** 2026-07-21
> **Source of truth for the domain:** `CONTROLE LEADS (1).xlsx` (repo root, gitignored — PII).
>
> **Ship record (2026-07-23):** All waves merged to `dev`→`main`→`prod` (tip `634d2daf`). Prod
> Supabase (`nyplttplcoyiiqjrvtiw`, schema `social_wiring`): migrations 025–029 applied, nav row
> `leads`→`producao` set, **12,177 leads + 23 sources imported** (1 import batch). Prod container
> `noctus-social-wiring` deployed on image revision `634d2daf`; `/api/leads` + analytics RPCs live
> (401-for-anon = route mounted + auth-guarded), `/leads` SPA route + chart chunks serve 200.
> Root-cause of the delayed launch: the VPS ran a 55-commit-stale pre-leads image that reported
> "healthy" (healthcheck only pings `/api/health`) — fixed by an ancestry-guarded `deploy_image`
> pull once a green prod build moved `:latest`. Lesson absorbed → `memory/feedback_healthcheck_blind_to_stale_image.md`.

---

## 1 · Goal

Turn a 29-sheet, 12,195-row real-estate lead-control spreadsheet into a first-class
managed surface in social-wiring: **Leads** — nav item directly under *Contatos*.
Manual day-of-entry stays the input mode (as in the sheet); the future wire-up to the
Meta / social integrations is explicitly **out of scope for now** but the schema is
shaped so it slots in without a rewrite.

The spreadsheet is organizationally sound (year → month → daily rows) but
lexically dirty: **75 distinct `ORIGEM` spellings collapse to ~15 real sources**
(`VIVA REAL` / `VIVAREAL` / `VIVAVREAL` / `VIVAVERAL` / `VIAREAL` / `VILA REAL` / `VR`
are one source). The module's core value is the **canonical dimension + editable alias
map**, so the charts show 15 series, not 75, and the user can refine the mapping in the UI.

## 2 · Decisions (ratified by the user, 2026-07-21)

| # | Decision | Rationale |
|---|---|---|
| D1 | Import **all 12,195 rows** + normalize; preserve the raw value on every row | 28 months of history make the graphs meaningful on day one; raw retained so a bad alias is always reversible |
| D2 | Persist to **Supabase, schema `social_wiring`** | The product's existing schema; the FE consumes it through the product API, never direct |
| D3 | Scope = **leads + leads-por-corretor only** | User: "both the others are included, just not now" |
| D4 | `vendas`/`fechamento` + `campanhas`/METRICAS (CPL, CPC, investimento) = **deferred**, schema seams left in place | User has upstream work to do first |
| D5 | Data model **faithful to the sheet** — `codigo_imovel`, `empreendimento`, `regiao`, `corretor`, `anuncio_tier`, `novo`/`retorno` are first-class typed columns | Best analytics; charting leads-por-empreendimento requires real columns, not JSON |
| D6 | The `.xlsx` is **gitignored, never committed** | 12k client names + phone numbers — LGPD. Import runs locally against Supabase |

## 3 · Domain model (derived from the sheet)

Column layout drifts across the 29 sheets (5 distinct header shapes) but the semantics are stable.
`ORIGEM` is **column index 2 in all 29 sheets** — verified empirically, use it as the anchor for shape detection.

| Sheet concept | Column | Notes |
|---|---|---|
| `DATA` | 0 | Excel serial (`46204.0`) in most sheets; `dd.mm.yy` strings in `ABRIL_24` / ` MARÇO_24` |
| `CODIGO` | 1 | `"ONE9622 Bosque dos Manacás - Km 21"` → split into `codigo_imovel` + `empreendimento` + `regiao` |
| `ORIGEM` | 2 | 75 raw spellings → canonical source |
| `NOVO`/`RETORNO` | 3 (2026 sheets only) | Absent pre-2026; also leaks into `CLIENTE` as a `"Retorno "` name prefix |
| `CLIENTE` | 3 or 4 | |
| `CONTATO` | 4 or 5 | Phone (`" 11 99874.5536"`) or email |
| `CORRETOR`/`CONSULTOR` | 5 or 6 | ~15 brokers |
| `TIER` | 6 or 7 | `SIMPLES` / `DESTAQUE` / `SUPER DESTAQUE` |
| `OBSERVAÇÕES` / `FOLLOW UP` | 7 or 8 | Free text; `JULHO_2025` also has a follow-up **date** column |

**Canonical sources** (seed these; alias map absorbs the rest):
`senseys` · `zap` (ZAP / GRUPO ZAP / ZAP-VIVA REAL) · `viva-real` · `imovel-web` · `tempo-real` ·
`instagram-josi` · `instagram` · `site` · `whatsapp` · `v4` · `olx` · `facebook` · `loft` ·
`casa-mineira` · `indicacao` · `ligacao` · `tiktok` · `youtube` · `placa` · `follow-up` ·
`parceria` · `proprietario` · `outro`

Composite raws (`ZAP, IMOVEL WEB` · `GOOGLE/ WHATS` · `RETORNO/INSTAGRAM`) map to their **first**
recognizable token; `origem_raw` keeps the full string. `"ONE8137 - JARDIM COLIBRI - KM 26"` (135
occurrences in col 2) is a **data-entry error** — a código leaked into the origem column: map to
`outro` and flag `needs_review = true`.

## 4 · Schema (`social_wiring`) — migration `025_leads.sql`

Follows the `020_instagram_metric_snapshots.sql` RLS shape exactly: `SELECT` to `authenticated`
via `public.current_org_id()`, `ALL` to `service_role`. Forward-only + idempotent.
🔴 **Migration file only — not applied by the engineer.** Tech-lead applies via
`noctus.dev.migrate_product` with explicit consent.

### `lead_sources` — canonical origem dimension
`id` UUID PK · `org_id` UUID NOT NULL · `slug` TEXT · `label` TEXT · `categoria` TEXT
CHECK IN (`portal`,`social`,`direto`,`parceria`,`offline`,`outro`) · `cor` TEXT (hex, chart series color)
· `ativo` BOOL DEFAULT true · `ordem` INT DEFAULT 0 · `created_at`/`updated_at`
UNIQUE `(org_id, slug)`

### `lead_source_aliases` — the editable normalization map
`id` · `org_id` · `alias` TEXT (verbatim) · `alias_norm` TEXT (upper+trim+collapse-whitespace)
· `source_id` UUID FK→`lead_sources` ON DELETE CASCADE · `origem` TEXT CHECK IN (`seed`,`import`,`manual`)
· `created_at`
UNIQUE `(org_id, alias_norm)`

### `lead_corretores` — broker dimension
`id` · `org_id` · `nome` TEXT · `nome_norm` TEXT · `cor` TEXT · `ativo` BOOL · `created_at`/`updated_at`
UNIQUE `(org_id, nome_norm)`

### `lead_corretor_aliases`
`id` · `org_id` · `alias` · `alias_norm` · `corretor_id` FK ON DELETE CASCADE
UNIQUE `(org_id, alias_norm)` — absorbs `ALE`→`ALESSANDER`, trailing-space variants, typos

### `leads` — the fact table
```
id                UUID PK
org_id            UUID NOT NULL
data_entrada      DATE NOT NULL                    -- day of input (manual)
ano               SMALLINT GENERATED ALWAYS AS (EXTRACT(YEAR  FROM data_entrada)) STORED
mes               SMALLINT GENERATED ALWAYS AS (EXTRACT(MONTH FROM data_entrada)) STORED
codigo_raw        TEXT                             -- verbatim col 1
codigo_imovel     TEXT                             -- "ONE9622"
empreendimento    TEXT                             -- "Bosque dos Manacás"
regiao            TEXT                             -- "Km 21"
origem_id         UUID REFERENCES lead_sources(id) ON DELETE SET NULL
origem_raw        TEXT                             -- verbatim col 2 — NEVER overwritten
tipo_lead         TEXT CHECK IN ('novo','retorno','desconhecido') DEFAULT 'desconhecido'
cliente_nome      TEXT
contato           TEXT                             -- verbatim
contato_tipo      TEXT CHECK IN ('telefone','email','desconhecido')
contato_norm      TEXT                             -- digits-only phone, or lowercased email
corretor_id       UUID REFERENCES lead_corretores(id) ON DELETE SET NULL
corretor_raw      TEXT
anuncio_tier      TEXT CHECK IN ('simples','destaque','super_destaque')
status            TEXT
observacoes       TEXT
follow_up_data    DATE
follow_up_nota    TEXT
needs_review      BOOL NOT NULL DEFAULT false      -- unmapped origem / unparseable date / código-in-origem
source_sheet      TEXT                             -- "JULHO_26"  (provenance)
source_row        INT                              -- 1-indexed row (provenance)
import_batch_id   UUID REFERENCES lead_import_batches(id) ON DELETE SET NULL
created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at        TIMESTAMPTZ
```
**Idempotency key:** `UNIQUE (org_id, source_sheet, source_row) WHERE source_sheet IS NOT NULL`
— re-running the import upserts instead of duplicating. Manually-created leads have
`source_sheet IS NULL` and are exempt.

**Indexes:** `(org_id, data_entrada DESC)` · `(org_id, ano, mes)` · `(org_id, origem_id)` ·
`(org_id, corretor_id)` · `(org_id, empreendimento)` · `(org_id, needs_review) WHERE needs_review`
· GIN trigram on `cliente_nome` for the `q` search (enable `pg_trgm` if not present; if the
extension is unavailable fall back to `ILIKE` and say so in the return note).

### `lead_import_batches` — provenance / audit
`id` · `org_id` · `filename` TEXT · `sheets` INT · `rows_read` INT · `rows_inserted` INT ·
`rows_updated` INT · `rows_skipped` INT · `rows_flagged` INT · `status` TEXT CHECK IN
(`running`,`ok`,`erro`) · `erro` TEXT · `started_at` · `finished_at` · `created_by` UUID

### Deferred seams (D4) — leave these as commented section markers in the migration, no DDL
```
-- ── DEFERRED: vendas / fechamento ────────────────────────────────
--   lead_vendas(id, org_id, lead_id?, origem_id, empreendimento, unidade,
--               data_venda, valor, corretor_id)  → conversão lead→venda
-- ── DEFERRED: campanhas / METRICAS ───────────────────────────────
--   lead_campanhas(id, org_id, origem_id, periodo_inicio, periodo_fim,
--                  investimento, impressoes, cliques, cpc, leads, cpl,
--                  visitas_perfil, custo_visita, engajamento)  → CPL / ROI
```

## 5 · API contract — `/api/leads/*`

**Envelope (non-negotiable, matches `noctusai_lib.primitives.responses`):**
list endpoints → `paginated_response` → `{ data: T[], pagination: { page, page_size, total, total_pages } }`.
Single-item + analytics → `success_response` → `{ data: T }`. Errors → `AppException` (never raw `HTTPException(detail=dict)`).
All routes require auth. Auth tests assert **strict `== 401`**.

### 5.1 The canonical filter set
**Every** list + analytics endpoint accepts the SAME query params. Both engineers implement this
exact set — the FE filter bar and the BE query builder are one contract.

| Param | Type | Repeatable | Notes |
|---|---|---|---|
| `de` | date `YYYY-MM-DD` | no | inclusive lower bound on `data_entrada` |
| `ate` | date `YYYY-MM-DD` | no | inclusive upper bound |
| `ano` | int | **yes** | e.g. `?ano=2025&ano=2026` |
| `mes` | int 1–12 | **yes** | |
| `origem_id` | uuid | **yes** | |
| `corretor_id` | uuid | **yes** | |
| `tipo` | `novo`\|`retorno`\|`desconhecido` | **yes** | |
| `tier` | `simples`\|`destaque`\|`super_destaque` | **yes** | |
| `empreendimento` | string | **yes** | exact match on the normalized value |
| `regiao` | string | **yes** | |
| `needs_review` | bool | no | |
| `q` | string | no | free text over `cliente_nome`, `contato`, `codigo_raw`, `observacoes` |

Multiple values of the same param = **OR** within the dimension; different params = **AND** across dimensions.
Empty/absent = no constraint. Unknown param = ignored (never 422 — the FE adds params over time).

### 5.2 Endpoints

```
GET    /api/leads                      → paginated leads. Extra params: page, page_size (≤200, default 50),
                                          sort ∈ {data_entrada,cliente_nome,origem,corretor,created_at}
                                          (default data_entrada), order ∈ {asc,desc} (default desc)
POST   /api/leads                      → create (manual entry). Body = LeadCreate
GET    /api/leads/{id}                 → single
PATCH  /api/leads/{id}                 → partial update. Body = LeadUpdate
DELETE /api/leads/{id}                 → delete_response

GET    /api/leads/analytics/summary    → KPI tiles (§5.3)
GET    /api/leads/analytics/timeseries → ?grain=dia|mes|ano (default mes) [&split=origem|corretor|tipo|tier]
GET    /api/leads/analytics/by-dimension → ?dim=origem|corretor|empreendimento|regiao|tier|tipo
                                          [&limit=N default 15, rest folded into an "Outros" bucket]
GET    /api/leads/analytics/heatmap    → ano × mês matrix of counts

GET    /api/leads/sources              → list (not paginated → success_response)
POST   /api/leads/sources              → create
PATCH  /api/leads/sources/{id}         → update (label, categoria, cor, ativo, ordem)
DELETE /api/leads/sources/{id}         → 409 if leads still reference it unless ?reassign_to=<uuid>
GET    /api/leads/sources/aliases      → full alias map, ?unmapped=true → raw origens with no alias yet
POST   /api/leads/sources/aliases      → { alias, source_id } — creates/repoints; then re-links matching leads
DELETE /api/leads/sources/aliases/{id}

GET    /api/leads/corretores           → list, each with lead_count
POST   /api/leads/corretores
PATCH  /api/leads/corretores/{id}
DELETE /api/leads/corretores/{id}      → same 409/?reassign_to rule
GET/POST/DELETE /api/leads/corretores/aliases[/{id}]   → mirrors the source-alias endpoints

GET    /api/leads/facets               → distinct empreendimentos + regioes + anos present (for filter dropdowns)
                                          → { data: { empreendimentos: [{value,count}], regioes: [...], anos: [int] } }

GET    /api/leads/import/batches       → paginated import history
POST   /api/leads/import/preview       → multipart .xlsx → parses, returns the diff WITHOUT writing
POST   /api/leads/import/commit        → multipart .xlsx → parses + upserts, returns a batch record
```

### 5.3 Response shapes (TypeScript — the FE types are copied verbatim from this block)

```ts
export interface Lead {
  id: string; org_id: string;
  data_entrada: string;                // YYYY-MM-DD
  ano: number; mes: number;
  codigo_raw: string | null; codigo_imovel: string | null;
  empreendimento: string | null; regiao: string | null;
  origem_id: string | null; origem_raw: string | null;
  origem: { id: string; slug: string; label: string; cor: string | null } | null;  // joined
  tipo_lead: "novo" | "retorno" | "desconhecido";
  cliente_nome: string | null;
  contato: string | null; contato_tipo: "telefone" | "email" | "desconhecido" | null;
  corretor_id: string | null; corretor_raw: string | null;
  corretor: { id: string; nome: string; cor: string | null } | null;               // joined
  anuncio_tier: "simples" | "destaque" | "super_destaque" | null;
  status: string | null; observacoes: string | null;
  follow_up_data: string | null; follow_up_nota: string | null;
  needs_review: boolean;
  source_sheet: string | null; source_row: number | null;
  created_at: string; updated_at: string | null;
}

export interface LeadsSummary {
  total: number;
  novos: number; retornos: number;
  origens_ativas: number; corretores_ativos: number;
  empreendimentos: number;
  needs_review: number;
  periodo: { de: string | null; ate: string | null };
  // vs. the immediately-preceding window of equal length — null when unresolvable
  comparativo: { total_anterior: number; variacao_pct: number | null } | null;
  media_diaria: number;
  top_origem: { id: string; label: string; total: number; share_pct: number } | null;
  top_corretor: { id: string; nome: string; total: number } | null;
}

export interface TimeseriesPoint {
  bucket: string;          // "2026-07" (mes) | "2026-07-14" (dia) | "2026" (ano)
  label: string;           // "Jul/26" — pt-BR, ready to render on the axis
  total: number;
  series?: Record<string, number>;   // present only when ?split= is passed; key = slug|id
}
export interface TimeseriesOut {
  grain: "dia" | "mes" | "ano";
  split: string | null;
  // series metadata for the chart legend/colors — order IS the render order
  series_meta: { key: string; label: string; cor: string | null }[];
  points: TimeseriesPoint[];
}

export interface DimensionBucket {
  key: string; label: string; cor: string | null;
  total: number; share_pct: number;
  novos: number; retornos: number;
  variacao_pct: number | null;   // vs. the preceding window
}
export interface ByDimensionOut { dim: string; total: number; buckets: DimensionBucket[]; }

export interface HeatmapOut {
  anos: number[];
  // cells[ano][mes-1] — null where the month has no data at all (renders blank, not zero)
  cells: Record<string, (number | null)[]>;
  max: number;
}

export interface ImportBatch {
  id: string; filename: string; sheets: number;
  rows_read: number; rows_inserted: number; rows_updated: number;
  rows_skipped: number; rows_flagged: number;
  status: "running" | "ok" | "erro"; erro: string | null;
  started_at: string; finished_at: string | null;
}
export interface ImportPreview {
  filename: string; sheets: string[];
  rows_read: number; rows_new: number; rows_existing: number;
  rows_skipped: number;
  unmapped_origens: { alias: string; count: number }[];   // drive the "map these first" UI
  unmapped_corretores: { alias: string; count: number }[];
  sample: Lead[];        // first 20 parsed rows, unsaved
  warnings: string[];
}
```

**`share_pct` / `variacao_pct` are numbers already in percent** (`23.4`, not `0.234`), rounded to 1dp.
`variacao_pct` is `null` — never `0` — when the previous window has no data. The FE must render
`null` as `—`, never as `0%`.

## 6 · Frontend surface

Nav: new item **`{ name: "Leads", href: "/leads", icon: Target, route: "leads" }`** in the
`principal` group, **immediately after `Contatos`** — in BOTH `NAV_GROUPS` and `NAV_FALLBACK`
(`products/social-wiring/frontend/src/App.tsx`). Route registered in the `routes` array.
Migration `026_leads_nav_route.sql` inserts `('leads','producao')` into `status_pagina`
— without that row the seed's `filterNavByPageStatus` gate hides the item silently.

Page shell = **`SocialDashboardShell`** from `@noctusai/lib/design-system` (no networks prop —
single-network), with these subtabs:

| Subtab | Content |
|---|---|
| **Visão Geral** | KPI row (total · novos vs retornos · média diária · top origem · variação) · evolução mensal (area, split by origem) · donut por origem · barras top-10 corretores · heatmap ano×mês |
| **Base de Leads** | Sticky filter bar + paginated sortable table + row-click detail drawer + create/edit/delete + "revisar" quick-filter for `needs_review` |
| **Origens** | Stacked-area over time per source · table with share % + MoM delta · drill-in to a single source |
| **Corretores** | Ranking bar · share donut · per-broker evolution · table (the LEADS CORRETORES sheet, live) |
| **Empreendimentos** | Leads por empreendimento / região · treemap or ranked bars · drill-in |
| **Importação** | Drop an .xlsx → preview diff (incl. unmapped origens) → commit · batch history table |
| **Configuração** | Sources CRUD (label/categoria/**cor**/ativo/ordem) · alias map editor incl. "unmapped" queue · corretores CRUD + aliases |

**Global filter state is shared across subtabs** and mirrored into the URL query string, so a
filtered view is linkable and survives reload. One `useLeadsFilters()` hook owns it.

## 7 · Slices (wave 1 — file-disjoint, dispatched in parallel)

| Slice | Agent | Paths (disjoint) |
|---|---|---|
| **A · backend module** | `backend-engineer` | `products/social-wiring/backend/app/modules/leads/**`, `backend/migrations/025_leads.sql`, `026_leads_nav_route.sql`, `backend/app/main.py` (MODULES list only), `backend/tests/modules/leads/**` |
| **B · seed chart organs** | `frontend-engineer` | `seed/lib/frontend/src/design-system/charts/**` + `design-system/index.ts` (export block only) |
| **C · xlsx parser + alias seed data** | `backend-engineer` | `products/social-wiring/backend/app/modules/leads/importer/**` … *folded into A* — see §7.1 |

### 7.1 Why C folds into A
The parser's output shape IS the `leads` row shape, and the seed alias map IS migration data.
Splitting them puts the same contract in two heads. A single backend engineer owns
schema + parser + alias seed; the slice is large but internally coherent.

### 7.2 Wave 2 (after A and B integrate)
| Slice | Agent | Paths |
|---|---|---|
| **D · Leads pages** | `frontend-engineer` | `products/social-wiring/frontend/src/pages/leads/**`, `src/hooks/useLeads*.ts`, `src/App.tsx` |

D is wave 2 because it must `import` B's organs to compile, and types itself against A's contract.
The contract in §5.3 is frozen — D does not wait for A to be *live*, only for B to be *merged*.

## 8 · Seed-first note (recurrence rule, N=3)

`MetricCard`-style KPI tiles and recharts wrappers are hand-rolled in **three** products already
(`social-wiring` inline · `personal-finance/components/charts/*` · `erp-imobiliario/components/ui/chart.tsx`).
Building a fourth product-local set is the forbidden 4th instance → **Slice B builds them once in
the seed** (`@noctusai/lib/design-system/charts`) and Leads is their first consumer.
Migrating the three existing consumers is NOT in this build — it follows the pilot-products-first
cadence as a separate slice. Logged so it does not dangle.

## 9 · Decision log

- **2026-07-21** — D1–D6 ratified by the user (see §2).
- **2026-07-21** — Slice C folded into A (§7.1).
- **2026-07-21** — Chart organs go to the seed, not the product (§8, recurrence rule N=3).
