# 02 — Platform Landscape

> Quick orientation for any agent or developer entering this codebase.
> **Counts last verified:** 2026-04-18 (via `find` on the actual file tree). **Products table last verified:** 2026-05-10.

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
| **AdConnect** | `products/adconnect/` | B2B ad-inventory marketplace (custom JWT auth; MVP in flight on `adconnect-mvp-implementation`) | 8007/8130 | `adconnect` |
| **Dev Team** | `products/dev-team/` | agno multi-agent dev team (engine at `dev_team/`, MCP exposure `noctus.team.*`; switch-flip gated by `ANTHROPIC_API_KEY`; frontend port off-pattern — see `vite.config.ts`) | 8009/8123 | `dev_team` |
| **YouTube Crawler** | `products/youtube-crawler/` | YouTube Data API v3 + Drive + WAHA + SMTP — quota-aware uploads with Fernet-encrypted refresh tokens (scaffolded 2026-05-05; containerized 2026-05-10 follow-up of `containerization-backlog-closure`) | 8008/8150 | `youtube_crawler` |
| **Media Scheduling** | `products/media-scheduling/` | Real-estate media-crew scheduling via WhatsApp ↔ OpenAI ↔ Google Calendar (ported 2026-05-04 from sibling repo `whatsapp-google-scheduling/` via `projects/media-scheduling-port/`) | 8096/8140 | `media_scheduling` |
| **Imobi Scheduling** | `products/imobi-scheduling/` | WhatsApp chatbot scheduling real-estate media crews via OpenAI tool-loop + Google Calendar + Maps travel-time; first chatbot consumer of `noctusai_lib.{integrations.whatsapp,domain.chatbot,domain.scheduling}`; folded 2026-05-11 from sibling repo `whatsapp-google-scheduling/` via `projects/imobi-scheduling-bot-creation/`; single-agency v1, WhatsApp-only (admin UI deferred) | 8011/8160 | `imobi_scheduling` |

> **Port allocation table** of record: `RESERVED_RANGES` in `mcp/noctusai/tools/noctus/dev/scaffold.py`. The `noctus.dev.reserve_port_range` MCP tool consults that list when scaffolding new products; this table mirrors it.

Architecture, stack, tenant isolation, and shared packages: see `03-SEED-ARCHITECTURE.md` and the patterns under `PATTERNS/`.

## Inventory

> Auto-updated by `scripts/update-kb-counts.py` on every commit (pre-commit hook). Do not edit between the markers.

<!-- kb-counts:start:inventory -->
| Product | Routers | Services | Pages | Hooks | Test files | Test fns |
|---------|---------|----------|-------|-------|-----------|---------|
| Core | 28 | 12 | 26 | 0 | 39 | 439 |
| ERP | 59 | 52 | 67 | 66 | 113 | 1,665 |
| PF | 15 | 17 | 30 | 16 | 45 | 464 |
| Therapy | 40 | 45 | 65 | 33 | 78 | 1,095 |
| Seed | 2 | 1 | 8 | 1 | 5 | 10 |
| Daily Life | 6 | 7 | 11 | 7 | 14 | 200 |
| Mailing | 10 | 10 | 21 | 9 | 16 | 192 |
| AdConnect | 9 | 10 | 16 | 5 | 25 | 216 |
| Dev Team | 0 | 2 | 6 | 0 | 3 | 45 |
| Media Scheduling | 5 | 8 | 10 | 3 | 15 | 78 |
| YouTube Crawler | 0 | 0 | 7 | 0 | 3 | 0 |
| Imobi Scheduling | 3 | 13 | 8 | 1 | 22 | 272 |
| **Total** | **177** | **177** | **275** | **141** | **378** | **4,676** |
<!-- kb-counts:end:inventory -->

## Database

<!-- kb-counts:start:database -->
- **Schemas (12):** `public` + `erp` + `personal-finance` + `therapy` + `daily_life` + `mailing` + `seed` + `adconnect` + `dev_team` + `media_scheduling` + `youtube_crawler` + `imobi_scheduling`.
- **Tables: 311** distributed across the schemas.
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
