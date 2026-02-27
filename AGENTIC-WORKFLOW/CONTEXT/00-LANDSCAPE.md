# 00 — Platform Landscape

> System overview for any AI agent or developer entering this codebase.

---

## What Is NoctusAI?

A **multi-tenant, multi-product SaaS platform**. Organizations sign up once on the core platform and get access to licensed products. Each product is independently deployable but shares authentication, tenant context, and billing through the core.

---

## Products

| Product | Path | Description | Port (BE) | Port (FE) |
|---------|------|-------------|-----------|-----------|
| **Core Platform** | `core/` | Auth, orgs, billing, licenses, SSO, admin | 8000 | 5173 |
| **ERP Imobiliario** | `products/erp-imobiliario/` | Real estate CRM: clients, properties, matching, sales funnel | 8001 | 8080 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Core Platform                         │
│  Auth · Orgs · Billing · Licenses · SSO · Admin          │
│  FastAPI :8000          React :5173                      │
└──────────────┬──────────────────────────┬───────────────┘
               │ SSO Token                │
┌──────────────▼──────────────────────────▼───────────────┐
│               ERP Imobiliario                            │
│  Clients · Properties · Matching · Sales Funnel · AI     │
│  FastAPI :8001          React :8080                      │
└─────────────────────────────────────────────────────────┘
               │                    │
       ┌───────▼────────┐  ┌───────▼────────┐
       │   Supabase      │  │  External SVCs  │
       │   PostgreSQL     │  │  OpenAI · WAHA  │
       │   RLS per org    │  │  n8n · Stripe   │
       └─────────────────┘  └─────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Frontend | React 18 + TypeScript + Vite |
| Database | Supabase (PostgreSQL + RLS) |
| Styling | Tailwind CSS + shadcn/ui |
| Server State | TanStack Query (ERP), React Context (Core) |
| Client State | Zustand (ERP), React Context (Core) |
| Auth | Supabase Auth + JWT + SSO tokens |
| AI | OpenAI GPT-4o-mini + text-embedding-3-small |
| Messaging | WAHA (WhatsApp HTTP API) |
| Orchestration | n8n (self-hosted) |
| Billing | Stripe |

---

## Tenant Isolation

- Every user belongs to exactly one organization (`noctus_users.org_id`)
- Supabase RLS policies scope all data queries to the user's `org_id`
- Admin operations use `get_admin_client()` (service role key, bypasses RLS)
- User operations use `get_user_client(token)` (respects RLS)

---

## Shared Infrastructure

- **Single root `.env`** — All backends read from one `.env` at repo root via absolute path in `config.py`
- **Single root `venv/`** — Shared Python virtual environment, `requirements.txt` at root
- **Per-backend `requirements.txt`** — Kept for independent Docker deploys
- **Frontend env** — `VITE_`-prefixed vars in per-frontend `.env` files (end up in browser bundles)

---

## External Services

| Service | URL | Purpose |
|---------|-----|---------|
| Supabase | `*.supabase.co` | Database, auth, storage |
| n8n | `n8n.noctusai.com` | Agentic workflow orchestration |
| WAHA | `waha.noctusai.com` | WhatsApp messaging API |
| OpenAI | `api.openai.com` | AI descriptions, embeddings, lead scoring |
| Stripe | `api.stripe.com` | Billing, subscriptions, checkout |

---

## Language Convention

- **Portuguese (Brazilian)** for business domain: clientes, metas, ativos, funil, permutas, comissoes
- **English** for technical/framework concepts: routers, services, hooks, stores
- **Error messages** returned to users are in Portuguese
