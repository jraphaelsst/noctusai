# Monica — MASTER-PROMPT

> Authoritative development guide for Monica, the CRM of Mônica Tangerino's psychoanalysis practice.

## Purpose

Monica Tangerino is a psychoanalyst who talks about life's important matters through psychoanalysis (Instagram `@psimonicatangerino` professional, `@monicatangerino` personal). Monica (the product) is her practice CRM — today leads, WhatsApp conversations and her own context; later an ERP (finance already mounted, hidden behind `status_pagina`). First product of the org "Mônica Tangerino" (`fa80a1e0-1bcd-4c65-8a37-2162e8ffa688`). pt-BR UI; the audience is deliberately NOT narrowed in copy.

**Seed-first, strictly.** Every screen and every backend surface is a seed organ; the product only wires them (config, auth, the two seams below). If an organ lacks something, add a named seam IN THE SEED (the way `on_message` was added to the inbox), never a product fork.

## Architecture

### Backend

```
products/monica/backend/app/
  main.py                      → create_product_app + mount_leads + mount_clients + mount_finance + the routers below
  config.py                    → SeedSettings: ENCRYPTION_KEY, MONICA_WAHA_*, REDIS_URL, AGENTS_*, MONICA_AGENT_KEY
  crm.py                       → LEADS_CONFIG: stages lead/atendimento/negociacao/fechado (colour + tag Lead/Em atendimento/Paciente), origins whatsapp/instagram/indicacao/outro; CLIENTS_CONFIG (Paciente/Pacientes, America/Sao_Paulo); on_stage_entered: fechado -> ClientsService.ensure_from_lead
  routers/whatsapp_router.py   → seed connections router (admin via make_organ_auth) + seed inbox router
  routers/contexto_router.py   → /api/contexto: proxy to agents org specs, forwards the USER's bearer
  services/whatsapp_leads.py   → on_new_chat -> LeadsService.upsert_from_whatsapp; on_message -> touch_last_message; on_purge -> LeadsService.purge_from_whatsapp
```

- **inbox → leads**: `on_new_chat` fires once per chat first created by an inbound non-group message (atomic claim on the chat row); a deleted lead is NOT recreated (intended — the chat row persists). `on_message` (seed seam, added with this product) fires for every newly stored message, inbound and outbound.
- **WAHA**: Monica's own instance via `MONICA_WAHA_BASE_URL`; no default; unset ⇒ 503. Never the shared CORE-tier instance (single session, social-wiring's "One Chat" number). Realtime: Redis if `REDIS_URL`, else an explicit single-worker declaration, else the boot refuses.
- **Contexto**: org specs of the agent definition `monica-leads` (agents `agent_version_specs` declare the fields, `agent_org_specs` hold the values). The agent itself is later; the definition is not activated on any channel.
- Errors: agents' 422 is re-emitted flat `{detail, code, **fields}`; refused token 403; no agents link 503; agent not created for the org 404.

### Frontend

```
products/monica/frontend/src/
  App.tsx                 → nav groups Principal / Leads / Pacientes / Gestão / Configurações (status_pagina route keys)
  lib/crm.ts              → the hooks, built once: createLeadsHooks, createWhatsAppInboxHooks, createWhatsAppConnectionsHooks, createOrgSpecsHooks, createClientsHooks
  pages/Leads.tsx         → /leads/* Funil + Lista sharing one filter state
  pages/Pacientes.tsx     → /pacientes/* seed ClientsList / ClientsAgenda / ClientDetailPage (tab in ?aba=), ?lead= resolves a converted lead
  pages/Conversas.tsx     → seed WhatsAppInbox, ?chat= deep link, "Ver lead" header slot
  pages/Contexto.tsx      → seed OrgSpecsForm
  pages/Configuracoes.tsx → seed SectionTabsPage (sub-routes), section Conexões (admin only)
```

### Database (schema `monica`)

`status_pagina`, `invitations`, finance (`fin_*`, 012), `leads` (014), `whatsapp_connections|chats|messages` (015), CRM `status_pagina` rows (016), per-app switch `app_enabled`/`session_role` + `leads.edited_at` (017), pacientes `clients|client_schedules|client_sessions|client_payments` (018 — session receivables go through the finance `FinanceBooking` seam, source `external`, ref `clients:session:<id>`), `pacientes`/`pacientes_agenda` status_pagina rows (019). RLS org-scoped on `public.current_org_id_for('monica')`; browser roles read, the backend writes with the service role.

## Rules

- No product-local re-implementation of an organ; no `isLoading`; every write is a `useCacheWriteMutation` (the organs already are).
- Auth tests assert strict `== 401`.
- LGPD: conversations are health-adjacent personal data — never log message bodies, never put them in audit payloads.
- The WAHA base URL / session / HMAC come from env; a missing one fails loud, never a Fake.
- First go-live follows `KB § GUIDES/production-deploy.md § 5a` (serve first, flip `deploy_scope='live'` in core admin LAST).

## Testing

```bash
cd products/monica/backend && pytest
cd products/monica/frontend && npx vitest run && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`; Frontend: `@noctusai/lib` + `@noctusai/seed`.
