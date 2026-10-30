# Core Platform

Central platform for authentication, organization management, billing, licensing, and SSO. Serves as the admin dashboard and gateway to all NoctusAI products.

## Stack

- **Backend**: FastAPI (port 8000)
- **Frontend**: React + TypeScript + Vite (port 5173)
- **Database**: Supabase (schema: `public`). `org_settings` (vendor credentials), `webhook_endpoints`, `webhook_deliveries` and `api_keys` are **service-role only** (migration 086): no anon/authenticated grant or policy; every access goes through the API's admin-gated routes. `ai_usage` (migration 091) is the central append-only LLM usage ledger of every product -- service-role insert, member/platform-admin read, read by `/api/admin/llm-usage`
- **Tenant key**: `org_id`
- **Auth**: Custom REST API

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8000 --app-dir products/core/backend

# Frontend
cd products/core/frontend && npm run dev
```

## Key Features

- Organization creation and management
- Org brand identity (`/api/brand`, page `/org-settings/identidade`): one visual identity per org — colors, fonts, radius, logos, favicon, derived dark mode — applied to core and every product by the seed `BrandProvider`; NOC standard when unset; `.md`/`.pdf` design-system upload analyzed by Claude into a validated, versioned draft
- Admin > Templates (`/api/admin/templates`, page `/admin/templates/*`, migration 092): DB-backed, versioned platform template library by kind (design system, agents/prompts, messages, documents, repo/workflow) and scope (platform or product); edit = new version, activate archives the previous; design-system templates seeded from the NOC standard tokens and validated with the brand-token rules; a read-only "Fontes" catalogue lists template-like assets that still live outside the DB. The filesystem scaffold browser moved to `/api/admin/template-scaffolds`
- Platform Operação (`/api/admin/operations`, page `/admin/operacao`, platform admins): every product's scheduled jobs from the seed scheduler run ledger (`public.scheduler_runs` / `public.scheduler_jobs`, failures alert admins in-app at most once per job per 6h), container health (`/api/fleet`), the seed model catalog, LLM spend + cost ledger, and the owner daily brief (07:00 platform tz, code-only — no LLM; in-app + e-mail, history in `public.owner_briefs`, dead-man after 26h without an ok run)
- User authentication and session handling (one cross-tab-locked refresh, `refreshCoreSession`; inactivity expiry ends only core's session via `POST /api/auth/logout?scope=local`, the "Sair" button ends every session)
- SSO token exchange for product access
- Stripe billing and subscription management
- Prepaid AI credit wallet (migration 093; page `/org-settings/creditos` "Créditos e uso", admin `/admin/creditos`): per-org balance in credits (default R$ 0,01 each) debited every minute from `ai_usage` (`core_credits_debit` job), usage shown org → product → feature in credits, R$ and tokens; top-ups by PIX/boleto/card on the existing Asaas/Stripe gateway (`POST /api/credits/purchase`, credited by the verified paid webhook); admin grants in credits or US$ through the same ledger path; modes `prepaid` / `postpaid_trusted` / `byok`. A prepaid org at/below its overdraft floor is refused (HTTP 402) by the seed `enforce_budget` guard, fail-closed
- Product licensing and provisioning
- Admin dashboard with platform-wide controls
- 7-role hierarchy (owner, admin, manager, member, viewer, dev, test)
- Team invitations and role assignment
- Notification system (platform-wide)
