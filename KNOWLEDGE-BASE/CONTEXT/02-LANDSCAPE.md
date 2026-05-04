# 02 — Platform Landscape

> Quick orientation for any agent or developer entering this codebase.
> **Counts last verified:** 2026-04-18 (via `find` on the actual file tree).

## Products

| Product | Path | Description | BE/FE Ports | Schema |
|---------|------|-------------|-------------|--------|
| **Core** | `products/core/` | Auth, orgs, billing, licenses, SSO, admin | 8000/5173 | `public` |
| **ERP** | `products/erp-imobiliario/` | Real estate CRM: clients, properties, matching, sales funnel, financial, WhatsApp | 8001/8080 | `erp` |
| **PF** | `products/personal-finance/` | Finance tracker: accounts, transactions, budgets, portfolios, watchlists | 8002/8090 | `personal-finance` |
| **Therapy** | `products/therapy-platform/` | Online therapy: video sessions, scheduling, clinical AI, wallets, messaging | 8003/8095 | `therapy` |
| **Seed** | `products/seed/` | Minimal reference implementation proving the shared stack | 8004/8100 | `seed` |
| **Daily Life** | `products/daily-life/` | Personal productivity hub: tasks, goals, habits, schedule, notes | 8005/8110 | `daily_life` |
| **Mailing** | `products/mailing/` | Email marketing: contacts, lists, templates, campaigns, automations | 8006/8120 | `mailing` |

> **AdConnect** (`products/adconnect/`) is a standalone scaffold, currently gitignored and not yet migrated into the monorepo structure. Not a live product. Excluded from the counts below.

Architecture, stack, tenant isolation, and shared packages: see `03-SEED-ARCHITECTURE.md` and the patterns under `PATTERNS/`.

## Inventory

> Auto-updated by `scripts/update-kb-counts.py` on every commit (pre-commit hook). Do not edit between the markers.

<!-- kb-counts:start:inventory -->
| Product | Routers | Services | Pages | Hooks | Test files | Test fns |
|---------|---------|----------|-------|-------|-----------|---------|
| Core | 28 | 12 | 26 | 0 | 38 | 423 |
| ERP | 59 | 52 | 68 | 66 | 110 | 1,646 |
| PF | 15 | 17 | 24 | 16 | 44 | 453 |
| Therapy | 40 | 44 | 66 | 29 | 75 | 976 |
| Seed | 0 | 0 | 8 | 0 | 3 | 31 |
| Daily Life | 7 | 7 | 12 | 7 | 15 | 226 |
| Mailing | 10 | 10 | 22 | 9 | 16 | 191 |
| **Total** | **159** | **142** | **226** | **127** | **301** | **3,946** |
<!-- kb-counts:end:inventory -->

## Database

<!-- kb-counts:start:database -->
- **Schemas (7):** `public` + `erp` + `personal-finance` + `therapy` + `daily_life` + `mailing` + `seed`.
- **Tables: 272** distributed across the schemas.
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
