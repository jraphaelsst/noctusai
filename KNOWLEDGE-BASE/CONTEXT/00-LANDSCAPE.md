# 00 — Platform Landscape

> Quick orientation for any agent or developer entering this codebase.

## Products

| Product | Path | Description | BE/FE Ports |
|---------|------|-------------|-------------|
| **Core** | `core/` | Auth, orgs, billing, licenses, SSO, admin | 8000/5173 |
| **ERP** | `products/erp-imobiliario/` | Real estate CRM: clients, properties, matching, sales funnel, financial, WhatsApp | 8001/8080 |
| **PF** | `products/personal-finance/` | Finance tracker: accounts, transactions, budgets, portfolios, watchlists | 8002/8090 |
| **Therapy** | `products/therapy-platform/` | Online therapy: video sessions, scheduling, clinical AI, wallets, messaging | 8003/8095 |
| **Seed** | `products/seed/` | Minimal reference implementation proving shared stack | 8004/8100 |
| **Daily Life** | `products/daily-life/` | Personal productivity hub: tasks, goals, habits, schedule, notes, focus | 8005/8110 |

Architecture, stack, tenant isolation, and shared packages: see **CLAUDE.md**.

## Inventory

| Product | Routers | Services | Tests | Test Files |
|---------|---------|----------|-------|------------|
| Core | 23 | 9 | 389 | 28 |
| ERP | 50 | 42 | 1,634 | 98 |
| PF | 16 | 14 | 473 | 37 |
| Therapy | 39 | 38 | 1,021 | 62 |
| Seed | 3 | 0 | 9 | 1 |
| Daily Life | 7 | 0 | TBD | 0 |
| **Total** | **138** | **103** | **3,526+** | **226** |

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

SQL scripts migrating data from old Django permutas platform into ERP. Run manually in Supabase SQL Editor. **264 imóveis** + **13 permutas** migrated. Markers: `titulo_anuncio LIKE '[MOCK]%'` (imóveis), `observacoes LIKE '%MIGRADO%'` (clientes/condominios).

## Language Convention

- **Portuguese (Brazilian)** for business domain: clientes, metas, ativos, funil, permutas, comissoes
- **English** for technical concepts: routers, services, hooks, stores
- **Error messages** returned to users are in Portuguese
