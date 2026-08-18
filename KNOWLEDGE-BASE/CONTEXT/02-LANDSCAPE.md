# 02 — Platform Landscape

> Quick orientation for any agent or developer entering this codebase.
> **Counts last verified:** 2026-04-18 (via `find` on the actual file tree).
> **Products table is hand-curated** (descriptions/status are human value) **but roster-vs-tree-parity is keeper-enforced** — `cli.py --verify-kb-sync` §4 ERRORS (commit-blocking) if any `products/<slug>/` on disk lacks a row here, so it cannot silently drift. The `## Inventory` + `## Database` blocks below ARE auto-derived (`kb-counts`, from the `start.sh` registry via `parse_products_registry()` + live schema counts).

## Products

| Product | Path | Description | BE/FE Ports | Schema |
|---------|------|-------------|-------------|--------|
| **Core** | `products/core/` | Auth, orgs, billing, licenses, SSO, admin | 8000/5173 | `public` |
| **ERP** | `products/erp-imobiliario/` | Real estate CRM: clients, properties, matching, sales funnel, financial, WhatsApp | 8001/8080 | `erp` |
| **PF** | `products/personal-finance/` | Finance tracker: accounts, transactions, budgets, portfolios, watchlists | 8002/8090 | `personal-finance` |
| **Therapy** | `products/therapy-platform/` | Online therapy: video sessions, scheduling, clinical AI, wallets, messaging | 8003/8095 | `therapy` |
| **Seed** | `products/seed/` | Minimal reference implementation proving the shared stack | 8004/8100 | `seed` |
| **Daily Life** | `products/daily-life/` | Personal productivity hub: tasks, goals, habits, schedule, notes | 8005/8110 | `daily_life` |
| **AdConnect** | `products/adconnect/` | B2B ad-inventory marketplace (custom JWT auth; MVP in flight on `adconnect-mvp-implementation`) | 8007/8130 | `adconnect` |
| **Dev Team** | `products/dev-team/` | agno multi-agent dev team (engine at `dev_team/`, MCP exposure `noctus.team.*`; switch-flip gated by `ANTHROPIC_API_KEY`; frontend port off-pattern — see `vite.config.ts`) | 8009/8123 | `dev_team` |
| **Social Wiring** | `products/social-wiring/` | Social-ops hub: email-marketing + WhatsApp-scheduling. Consolidation target of `media-scheduling`/`youtube-crawler`/`mailing`/`imobi-scheduling` (Wave 4, 2026-05-16) | 8011/8160 | `social_wiring` |
| **Knowledge Extractor** | `products/knowledge-extractor/` | Course-methodology RAG: Drive→transcribe→summarize→extract methodology→pgvector KB. Backend-only; absorbed from the sibling `knowledge-extractor` repo 2026-05-23 (seam-swap + container gate in flight, `container-first-codify-and-absorb-ke`) | 8012/8150 | `knowledge_extractor` |
| **IgIg** | `products/igig/` | Agency ERP for a communication agency: CRM/orçamentos, Central da Marca, planejamento editorial, esteira de produção criativa + portal de aprovação white-label, distribuição/métricas, financeiro/retainers. **Develops on SQLite** via the `noctusai_lib.integrations.persistence` seam (domain data only — auth stays on Supabase); migrates to Supabase later. Tenant isolation is app-layer `org_id` scoping on the SQLite path (accept-with-rationale) with real RLS policies shipped in the migrations for the Postgres path. Merges into `orbity` in the future | 8013/8170 | `igig` |
| **P Studio** | `products/p-studio/` | ERP for a real-estate photography/AV production studio: cadastros (clientes/imóveis/serviços/equipamentos), comercial funnel (`negocios`), shoot scheduling (`captacoes` + equipment checklist), production pipeline (`producoes`), financeiro with real bank billing. Billing goes through a `ProvedorCobranca` Protocol — Asaas is the only adapter allowed to know Asaas vocabulary, so the move to Banco do Brasil is an adapter swap. Absorbed 2026-08-13 from the sibling workspace `cadu/p-studio/` (project `p-studio-absorption-rollout`); schema + PostgREST exposure were already applied to the shared Supabase before absorption | 8014/8180 | `p_studio` |
| **Orbity** | `products/orbity/` | Agency operating-system (absorbing `sistema-orbity`): CRM/funil, clients, contracts, financeiro, agenda, WhatsApp automation, Meta ads, notifications — built seed-first via the absorption capability-uplift loop (in flight on `feat/orbity-build`, roadmap `project-history/roadmaps/orbity-2026-06.md`, knowledge `KB § ABSORPTIONS/orbity/`) | 8010/8140 | `orbity` |

> **Retired 2026-05-16** (`social-wiring-absorption` Wave 4): `media-scheduling`, `youtube-crawler`, `mailing`, `imobi-scheduling` were consolidated into **`social-wiring`** (`products/social-wiring/`). Email-marketing → `social-wiring/app/modules/email_marketing/`; WhatsApp-scheduling → `social-wiring/app/modules/scheduling/`. Core un-registration: forward migration `products/core/backend/migrations/033_retire_consolidated_products.sql` (013/028 immutable). Durable record: `project-history/ledger.ndjson` slug `social-wiring-absorption-wave4-teardown`.

> **Port allocation table** of record: `RESERVED_RANGES` in `mcp/noctusai/tools/noctus/dev/scaffold.py`. The `noctus.dev.reserve_port_range` MCP tool consults that list when scaffolding new products; this table mirrors it.

Architecture, stack, tenant isolation, and shared packages: see `03-SEED-ARCHITECTURE.md` and the patterns under `PATTERNS/`.

## Inventory

> Auto-updated by `noctus.dev.kb_sync` on every commit (pre-commit hook). Do not edit between the markers.

<!-- kb-counts:start:inventory -->
| Product | Routers | Services | Pages | Hooks | Test files | Test fns |
|---------|---------|----------|-------|-------|-----------|---------|
| Core | 29 | 14 | 29 | 0 | 51 | 559 |
| Erp Imobiliario | 63 | 57 | 68 | 69 | 132 | 1,857 |
| Personal Finance | 15 | 18 | 30 | 16 | 48 | 482 |
| Therapy Platform | 40 | 46 | 65 | 33 | 83 | 1,138 |
| Seed | 2 | 1 | 8 | 1 | 6 | 19 |
| Daily Life | 6 | 8 | 11 | 7 | 19 | 230 |
| Adconnect | 9 | 10 | 16 | 5 | 25 | 235 |
| Dev Team | 0 | 2 | 6 | 0 | 3 | 46 |
| Social Wiring | 20 | 33 | 97 | 63 | 137 | 1,903 |
| Knowledge Extractor | 4 | 12 | 13 | 4 | 17 | 96 |
| Orbity | 10 | 11 | 20 | 19 | 31 | 654 |
| Igig | 10 | 6 | 17 | 9 | 17 | 261 |
| P Studio | 8 | 8 | 11 | 1 | 19 | 311 |
| **Total** | **216** | **226** | **391** | **227** | **588** | **7,791** |
<!-- kb-counts:end:inventory -->

## Database

<!-- kb-counts:start:database -->
- **Schemas DECLARED in migrations (13):** `public` + `adconnect` + `daily_life` + `dev_team` + `erp` + `igig` + `knowledge_extractor` + `orbity` + `p_studio` + `personal-finance` + `seed` + `social_wiring` + `therapy`.
- **Tables: 433** declared across those schemas.
- Counted from `products/*/backend/migrations/*.sql` — this is what the
  REPO declares, not what is provisioned on the Supabase project. A
  schema can appear here and not exist live (unapplied migrations, or
  absent from PostgREST's exposed-schema setting).
<!-- kb-counts:end:database -->

- **RLS enabled on every table** — see `PATTERNS/backend/database-rls.md` for the canonical rules.

## External Services

| Service | Used By | Purpose |
|---------|---------|---------|
| Supabase | All | Database, auth, storage |
| OpenAI | ERP, Therapy | AI descriptions, embeddings, scoring, transcription, summaries |
| Stripe | Core, Therapy | Billing, subscriptions, marketplace payments |
| WAHA | ERP, Therapy | WhatsApp messaging (self-hosted at `waha.noctusai.com`) |
| Meta Business API | ERP | Facebook Lead Ads + campaign sync |
| Resend | All | Email delivery |
| LiveKit | Therapy | Video sessions (self-hosted) |
| n8n | External | Workflow orchestration (`n8n.noctusai.com`) |
| ClickSign/DocuSign/D4Sign | ERP | Digital signatures |

All integrations follow a **dry-run pattern**: services log actions and return mock responses when credentials are missing. **Credential resolution chain**: `org_settings` → `platform_settings` → env vars.

## Legacy Data Migration (`migratingDB/`)

SQL scripts migrating data from the old Django permutas platform into ERP. Run manually in Supabase SQL Editor. **264 imóveis** + **13 permutas** migrated. Markers: `titulo_anuncio LIKE '[MOCK]%'` (imóveis), `observacoes LIKE '%MIGRADO%'` (clientes/condominios).

## Language Convention

- **Portuguese (Brazilian)** for business domain: clientes, metas, ativos, funil, permutas, comissoes.
- **English** for technical concepts: routers, services, hooks, stores.
- **Error messages** returned to users are in Portuguese.
