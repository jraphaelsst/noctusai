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

> **Retired 2026-05-16** (`social-wiring-absorption` Wave 4): `media-scheduling`, `youtube-crawler`, `mailing`, `imobi-scheduling` were consolidated into **`social-wiring`** (`products/social-wiring/`). Email-marketing → `social-wiring/app/modules/email_marketing/`; WhatsApp-scheduling → `social-wiring/app/modules/scheduling/`. Core un-registration: forward migration `products/core/backend/migrations/033_retire_consolidated_products.sql` (013/028 immutable). Durable record: `project-history/ledger.ndjson` slug `social-wiring-absorption-wave4-teardown`.

> **Port allocation table** of record: `RESERVED_RANGES` in `mcp/noctusai/tools/noctus/dev/scaffold.py`. The `noctus.dev.reserve_port_range` MCP tool consults that list when scaffolding new products; this table mirrors it.

Architecture, stack, tenant isolation, and shared packages: see `03-SEED-ARCHITECTURE.md` and the patterns under `PATTERNS/`.

## Inventory

> Auto-updated by `noctus.dev.kb_sync` on every commit (pre-commit hook). Do not edit between the markers.

<!-- kb-counts:start:inventory -->
| Product | Routers | Services | Pages | Hooks | Test files | Test fns |
|---------|---------|----------|-------|-------|-----------|---------|
| Core | 28 | 13 | 27 | 0 | 47 | 499 |
| Erp Imobiliario | 60 | 53 | 67 | 67 | 127 | 1,798 |
| Personal Finance | 15 | 18 | 30 | 16 | 48 | 482 |
| Therapy Platform | 40 | 46 | 65 | 33 | 83 | 1,138 |
| Seed | 2 | 1 | 8 | 1 | 5 | 10 |
| Daily Life | 6 | 8 | 11 | 7 | 17 | 220 |
| Adconnect | 9 | 10 | 16 | 5 | 25 | 235 |
| Dev Team | 0 | 2 | 6 | 0 | 3 | 46 |
| Social Wiring | 8 | 19 | 14 | 8 | 43 | 431 |
| **Total** | **168** | **170** | **244** | **137** | **398** | **4,859** |
<!-- kb-counts:end:inventory -->

## Database

<!-- kb-counts:start:database -->
- **Schemas (9):** `public` + `adconnect` + `daily_life` + `dev_team` + `erp` + `personal-finance` + `seed` + `social_wiring` + `therapy`.
- **Tables: 303** distributed across the schemas.
<!-- kb-counts:end:database -->

- **RLS enabled on every table** — see `PATTERNS/database-rls.md` for the canonical rules.

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
