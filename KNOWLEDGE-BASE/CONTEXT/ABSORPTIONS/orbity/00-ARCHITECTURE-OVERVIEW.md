# 00 — Architecture Overview

## What Orbity is

**Orbity ("Gestão Para Agências")** is a multi-tenant, white-label SaaS that a Brazilian performance-marketing agency uses to run its **entire** business — and that the vendor (Senseys) **resells to other agencies**. It is not a single feature; it is an operating system for a marketing agency: lead-gen, paid-traffic ops, content/social production, client billing + Brazilian fiscal invoicing, team/HR with profit-sharing, and multi-channel client communication.

The product was originally (Sept 2025) a **single-tenant internal tool** for one agency, and multi-tenancy was retrofitted two days later. It has been actively developed daily through at least June 2026 (last migration `20260601…`).

## Stack

| Layer | Technology |
|---|---|
| Frontend | Vite + React 18 + TypeScript + shadcn/ui + Tailwind, **Lovable-generated** (`.lovable/`, `lovable-tagger`, `bun.lockb`) |
| State | TanStack Query v5 + 5 React Contexts + localStorage. No Redux/Zustand. |
| Backend | **Supabase only** — there is no separate API server. Postgres (RLS) + 73 Deno/TS **Edge Functions** + **pg_cron + pg_net** for scheduling |
| Auth | Supabase Auth (JWT); roles resolved from trusted tables |
| Hosting | Lovable-hosted FE (`sistema-orbity.lovable.app`); Supabase project ref `ovookkywclrqfmtumelw` |
| PWA | `vite-plugin-pwa` (installable, push via Firebase FCM) |

> **Architectural consequence for absorption:** the backend is Supabase-native (edge functions + pg_cron + RLS + DB triggers), which is a **divergent shape** from noc's FastAPI + seed-adapter + single-container model. A large share of behavior lives in pg_cron jobs and PL/pgSQL triggers, NOT in the FE or even in the edge-function TS — the migrations + cron schedule must be read to reconstruct runtime behavior. See `02-DATA-MODEL.md` §4 and `03-BACKEND-EDGE-FUNCTIONS.md` §cron.

## The three-tier multi-tenant model

```
MASTER  (Orbity / Senseys — the SaaS vendor, a hardcoded master agency_id)
  └── AGENCY  (the TENANT — a marketing agency, isolated by agency_id)
        ├── AGENCY USERS  (owner / admin / member ; job roles: gestor_trafego, designer, administrador)
        └── CLIENTS  (the agency's customers — businesses being marketed; DATA rows, NOT auth principals)
              ├── LEADS         (the client's prospects, captured via the agency's funnels)
              ├── CAMPAIGNS / TRAFFIC   (paid ads run on the client's behalf)
              ├── SOCIAL POSTS  (content produced + approved for the client)
              ├── CONTRACTS + PAYMENTS  (the agency↔client commercial relationship)
              └── PUBLIC REPORT (token-gated ads dashboard the end-client sees, no login)
```

**Key facts:**
- **The tenant is the AGENCY.** `agency_id` (UUID) is on every business table; isolation is by Postgres RLS.
- **Clients do not log in.** An agency's clients are records, not tenants. They interact only through **token-gated public links** (`/report/:token`, `/approve/:token`). There is no client portal at the auth/DB level.
- **One effective agency per user** (`get_user_agency_id()` uses `LIMIT 1`) — no active-org switching at the DB layer (a behavioral gap vs noc's multi-org-per-user; see `07-GAP-MAP`).
- **The MASTER tier is a hardcoded UUID check** (`MASTER_AGENCY_ID = 7bef1258…` = Senseys), not a real role. Orbity-the-company **dogfoods Orbity-the-product** to acquire/manage its agency customers (`orbity_leads` is the vendor's OWN sales pipeline; `master-whatsapp` is the vendor→agency support line).

### Roles (two axes)
- **Within an agency** — `agency_users.role ∈ {owner, admin, member}`; plus FE per-feature permissions (`agency_users.app_permissions` JSONB → 12 `canAccess*` booleans driven by role presets: Designer, Social Media, etc.).
- **Platform-global (vendor staff)** — `profiles.role ∈ {administrador, super_admin}`. ⚠️ `profiles.role` is **overloaded** — it carries BOTH intra-agency job roles (`gestor_trafego`/`designer`/`administrador`) AND the platform-global `super_admin`. `administrador` is treated as master. This conflation is a smell to untangle on absorption.

## The four businesses an agency runs (and Orbity's module for each)

A Brazilian performance-marketing agency runs **four businesses at once**. The throughline: *an agency's real product is repeatable operational discipline* — qualify every lead the same way, chase on a schedule, optimize on a cadence, bill on the 1st, report monthly, pay bonuses on measured results. Orbity encodes that discipline as automations + snapshots so it survives staff turnover and scale.

1. **A lead-gen machine** (per client) — capture (FB lead-ads / web forms / WhatsApp) → auto-qualify + score → feed quality back to Meta (CAPI) → chase via WhatsApp cadences until reply/convert. Kanban CRM, funnel/velocity/loss-reason analytics, cost-per-lead.
2. **An ad-ops shop** — connect FB ad accounts (OAuth) → sync campaigns/balances/leads → track per-client budget/result/situation → remind the gestor to optimize → hand the client a branded **public token report**.
3. **A content / social studio** — campaigns → posts (platform, schedule, hashtags) → role assignments → **client approval workflow** (public approve/revision links, expirations).
4. **A finance + HR back-office** — contracts (BR legal docs) → recurring/installment expenses, salaries, employees → monthly auto-billing → BR fiscal invoicing (Conexa/Asaas: notas fiscais, PIX, boletos, reconciliation) → dunning → **PPR profit-sharing** (net-profit pool gated by revenue + NPS, per-employee weighted scorecards). Plus tasks, agenda (Google Calendar sync), routines, reminders, NPS surveys, onboarding tour + help.

## Scale metrics

| Surface | Count |
|---|---|
| FE `.tsx` files | 433 (~365 domain + 68 shadcn/ui primitives) |
| FE domains (`src/components/*`) | ~27 |
| FE pages / routes | ~30 |
| React data hooks | ~50 |
| Supabase edge functions | 73 (of which 3 are deprecated stubs) |
| `_shared` edge lib modules | 11 |
| DB migrations | ~296 (2025-09-22 → 2026-06-01) |
| Final tables | 121 |
| DB functions | 69 |
| RLS policies | 406 (131 `ENABLE RLS`) |
| DB triggers | 108 |
| pg_cron jobs | 14 |

**Busiest domains** (by table count): WhatsApp/automation (~20), social-media/content (~16), tasks/agenda (~16), payments/finance (~15), clients/leads/CRM (~14), agency/billing-platform (~14).

**Most actively developed (May–June 2026):** an entirely new **WhatsApp automation flow engine** (`automation_flows`/`automation_steps`/`automation_executions`/`automation_pending_actions` + schedule windows + trigger conditions) that **replaced** the legacy bespoke ghosting/cadence cron workers (now disabled stubs). This is the richest single piece — see `01-PROCEDURES` §2.
