# NoctusAI Mailing — Implementation Checklist

> Email Marketing & Automacoes | Schema: `mailing` | Backend: 8006 | Frontend: 8120

---

## 1. Scaffold & Registration

- [x] Create `products/mailing/` using seed framework (not copy-paste)
- [x] Backend: main.py uses `create_product_app()` from `noctusai_seed`
- [x] Backend: config.py extends `ProductSettings`
- [x] Backend: database.py, dependencies.py, rate_limit.py delegate to framework
- [x] Backend: tests passing (3/3)
- [x] Create `products/mailing/README.md`
- [x] Create `products/mailing/MASTER-PROMPT.md`
- [ ] Create `products/mailing/frontend/.env.example`
- [x] Register in `start.sh` (backend 8006 + frontend 8120)
- [x] Add Mailing row to `CLAUDE.md` architecture table
- [ ] Create `KNOWLEDGE-BASE/CONTEXT/backend/09-MAILING.md`

---

## 2. Database Migration (`001_mailing.sql`)

### Platform tables (from seed pattern)
- [ ] `mailing.status_pagina` — feature flags
- [ ] `mailing.invitations` — team invites

### Domain tables
- [ ] `mailing.contacts` — email, nome, empresa, tags[], custom_fields, status, source
- [ ] `mailing.contact_lists` — static lists + dynamic segments (filtros JSONB)
- [ ] `mailing.contact_list_members` — join table contato <> lista
- [ ] `mailing.templates` — HTML templates com variaveis `{{nome}}`
- [ ] `mailing.campaigns` — rascunho > agendada > enviando > enviada > pausada > cancelada
- [ ] `mailing.automations` — trigger_type, trigger_config, status
- [ ] `mailing.automation_steps` — send_email, wait, condition, add_tag, remove_tag, webhook
- [ ] `mailing.automation_enrollments` — contact in automation + current step + next_action_at
- [ ] `mailing.send_logs` — per-recipient: queued > sent > delivered > opened > clicked > bounced
- [ ] `mailing.link_clicks` — individual link click tracking
- [ ] `mailing.unsubscribes` — audit trail (LGPD)
- [ ] `mailing.sender_domains` — domain verification tracking

### RLS & Indexes
- [ ] RLS policies on all tables (org_id via JWT)
- [ ] GIN index on contacts.tags
- [ ] Index on send_logs.campaign_id
- [ ] Index on send_logs.resend_message_id
- [ ] Index on automation_enrollments.next_action_at WHERE active
- [ ] Unique constraint contacts(org_id, email)
- [ ] Unique constraint contact_list_members(list_id, contact_id)
- [ ] Unique constraint automation_enrollments(automation_id, contact_id)

---

## 3. Backend — Config & Infrastructure

- [ ] `app/config.py` — MailingSettings (resend_api_key, webhook_secret, send limits, scheduler intervals)
- [ ] `app/database.py` — get_supabase_client(schema="mailing") + get_core_client()
- [ ] `app/dependencies.py` — get_current_user, get_org_id, get_user_role, get_admin_client
- [ ] `app/main.py` — app factory with lifespan (scheduler start/stop)
- [ ] `app/rate_limit.py` — create_limiter
- [ ] `app/responses.py` — re-export from noctusai_lib
- [ ] `app/scheduler.py` — APScheduler (3 jobs: send loop 30s, scheduled campaigns 1min, automations 5min)
- [ ] `app/credential_resolver.py` — per-org Resend API key resolution

---

## 4. Backend — Routers

### Platform routers (from seed)
- [ ] `routers/health.py` — GET /api/health
- [ ] `routers/team.py` — team management (invites, members, remove)
- [ ] `routers/notificacoes.py` — notification proxy to core

### Domain routers
- [ ] `routers/contacts.py` — CRUD, search/filter, import CSV, sync
- [ ] `routers/lists.py` — CRUD, add/remove members, resolve contacts (static + dynamic)
- [ ] `routers/templates.py` — CRUD, preview with variables, send test email
- [ ] `routers/campaigns.py` — CRUD, schedule, send, pause, cancel, stats
- [ ] `routers/automations.py` — CRUD, steps CRUD, reorder, activate/pause, enroll contacts
- [ ] `routers/analytics.py` — dashboard metrics, campaign stats, automation funnel, contact activity
- [ ] `routers/webhooks.py` — Resend event receiver (no auth, signature verification)
- [ ] `routers/unsubscribe.py` — public unsubscribe page (no auth, HMAC token)
- [ ] `routers/settings.py` — sender domains CRUD, sender config, domain verification

---

## 5. Backend — Services

- [ ] `services/contact_service.py` — CRUD, search, filter by status/tags/source
- [ ] `services/list_service.py` — CRUD lists, resolve dynamic segments (run filter query)
- [ ] `services/template_service.py` — CRUD, `{{var}}` interpolation, preview rendering
- [ ] `services/campaign_service.py` — lifecycle (create > schedule > send > complete), stats aggregation
- [ ] `services/send_service.py` — **core engine**: resolve recipients, create send_logs, Resend Batch API (100/batch), rate limiting
- [ ] `services/automation_service.py` — lifecycle, steps management, enrollment, step execution
- [ ] `services/analytics_service.py` — aggregations, time series, open/click/bounce rates
- [ ] `services/webhook_service.py` — process Resend events > update send_logs + contacts status
- [ ] `services/import_service.py` — CSV parse, validate, batch create contacts
- [ ] `services/sync_service.py` — pull contacts from ERP/other products (service_role)
- [ ] `services/unsubscribe_service.py` — HMAC token generation/validation, process unsubscribe, audit log

---

## 6. Backend — Schemas (Pydantic)

- [ ] `schemas/contacts.py` — ContactCreate, ContactUpdate, ContactResponse, ContactImport
- [ ] `schemas/lists.py` — ListCreate, ListUpdate, ListResponse, DynamicFilter
- [ ] `schemas/templates.py` — TemplateCreate, TemplateUpdate, TemplateResponse, TemplatePreview
- [ ] `schemas/campaigns.py` — CampaignCreate, CampaignUpdate, CampaignResponse, CampaignStats
- [ ] `schemas/automations.py` — AutomationCreate, StepCreate, StepUpdate, EnrollmentResponse
- [ ] `schemas/analytics.py` — DashboardMetrics, CampaignAnalytics, TimeSeriesPoint

---

## 7. Backend — Tests

- [ ] `tests/conftest.py` — fixtures, MockSupabaseClient, AuthClient
- [ ] `tests/routers/test_health.py`
- [ ] `tests/routers/test_team_router.py`
- [ ] `tests/routers/test_contacts.py`
- [ ] `tests/routers/test_lists.py`
- [ ] `tests/routers/test_templates.py`
- [ ] `tests/routers/test_campaigns.py`
- [ ] `tests/routers/test_automations.py`
- [ ] `tests/routers/test_analytics.py`
- [ ] `tests/routers/test_webhooks.py`
- [ ] `tests/routers/test_unsubscribe.py`
- [ ] `tests/routers/test_settings.py`
- [ ] `tests/services/test_send_service.py`
- [ ] `tests/services/test_template_service.py`
- [ ] `tests/services/test_webhook_service.py`
- [ ] `tests/services/test_import_service.py`

---

## 8. Frontend — Infrastructure

- [ ] `src/main.tsx` — env validation, render App
- [ ] `src/App.tsx` — routes (public + authenticated)
- [ ] `src/index.css` — Tailwind imports
- [ ] `src/integrations/supabase/client.ts` — createProductSupabase("mailing")
- [ ] `src/store/authStore.ts` — createAuthStore()
- [ ] `src/lib/api-client.ts` — createApiClient (port 8006)
- [ ] `src/lib/constants.ts`
- [ ] `src/lib/utils.ts`
- [ ] `src/components/auth/AuthProvider.tsx`
- [ ] `src/components/ErrorBoundary.tsx`
- [ ] `src/components/NotificationBell.tsx`
- [ ] `src/hooks/useNotificacoes.ts`

---

## 9. Frontend — Layout

- [ ] `src/components/layout/Layout.tsx` — AppShell + Sidebar (Mail icon) + Header + nav groups:
  - Principal: Dashboard, Contatos, Listas
  - Marketing: Templates, Campanhas, Automacoes
  - Insights: Analytics
  - Configuracao: Settings, Equipe

---

## 10. Frontend — Pages

### Auth pages (from seed)
- [ ] `src/pages/Landing.tsx`
- [ ] `src/pages/Login.tsx`
- [ ] `src/pages/SSOCallback.tsx`
- [ ] `src/pages/AcceptInvite.tsx`
- [ ] `src/pages/ForgotPassword.tsx`
- [ ] `src/pages/NotFound.tsx`

### Domain pages
- [ ] `src/pages/Dashboard.tsx` — metric cards (total contacts, sent, open rate, click rate), recent campaigns
- [ ] `src/pages/Contacts.tsx` — table with search/filter, import CSV modal, tag management
- [ ] `src/pages/ContactDetail.tsx` — contact data + send history + activity timeline
- [ ] `src/pages/Lists.tsx` — list of lists/segments, create modal, member count
- [ ] `src/pages/Templates.tsx` — template list, create/edit
- [ ] `src/pages/TemplateEditor.tsx` — HTML editor + variable preview + send test
- [ ] `src/pages/Campaigns.tsx` — campaign list with status badges
- [ ] `src/pages/CampaignCreate.tsx` — select template + list, schedule or send now
- [ ] `src/pages/CampaignDetail.tsx` — live stats (sent, opened, clicked, bounced)
- [ ] `src/pages/Automations.tsx` — automation list with status
- [ ] `src/pages/AutomationCreate.tsx` — trigger config + step builder
- [ ] `src/pages/AutomationDetail.tsx` — steps view + enrollment table
- [ ] `src/pages/Analytics.tsx` — charts (recharts): open rate, clicks, bounces, growth
- [ ] `src/pages/Settings.tsx` — domain verification, sender config
- [ ] `src/pages/Equipe.tsx` — team management (from seed)
- [ ] `src/pages/Unsubscribe.tsx` — public page, no auth

---

## 11. Frontend — Hooks (TanStack Query)

- [ ] `src/hooks/useContacts.ts` — list, create, update, delete, import
- [ ] `src/hooks/useLists.ts` — list, create, update, delete, members
- [ ] `src/hooks/useTemplates.ts` — list, create, update, delete, preview
- [ ] `src/hooks/useCampaigns.ts` — list, create, update, schedule, send, pause, cancel, stats
- [ ] `src/hooks/useAutomations.ts` — list, create, steps CRUD, activate/pause, enroll
- [ ] `src/hooks/useAnalytics.ts` — dashboard, campaign stats, automation funnel

---

## 12. Frontend — Components

- [ ] `src/components/contacts/ContactTable.tsx`
- [ ] `src/components/contacts/ContactImportModal.tsx`
- [ ] `src/components/contacts/ContactDetail.tsx`
- [ ] `src/components/lists/ListForm.tsx`
- [ ] `src/components/lists/DynamicFilterBuilder.tsx`
- [ ] `src/components/templates/TemplateEditor.tsx`
- [ ] `src/components/templates/TemplatePreview.tsx`
- [ ] `src/components/campaigns/CampaignForm.tsx`
- [ ] `src/components/campaigns/CampaignStats.tsx`
- [ ] `src/components/automations/AutomationStepList.tsx`
- [ ] `src/components/automations/StepConfigPanel.tsx`
- [ ] `src/components/automations/EnrollmentTable.tsx`
- [ ] `src/components/analytics/MetricCard.tsx`
- [ ] `src/components/analytics/OpenRateChart.tsx`

---

## 13. Verification

- [ ] `cd products/mailing/backend && pytest` — all tests passing
- [ ] Backend starts: `uvicorn app.main:app --reload --port 8006`
- [ ] Frontend starts: `npm run dev` on port 8120
- [ ] E2E: create contact > create template > create campaign > send test > verify send_logs
- [ ] E2E: create automation with 3 steps > activate > enroll contact > verify step execution
- [ ] E2E: add domain > verify DNS records > confirm verification
- [ ] Unsubscribe flow: click link > confirm > contact status updated
- [ ] Webhook: simulate Resend event > send_log status updated

---

## 14. Roadmap — Features Avancadas (future)

### Automacao & Inteligencia
- [ ] Smart Send Time — send at optimal time per contact based on open history
- [ ] Re-send to unopened — auto re-send with different subject
- [ ] Lead scoring by engagement — auto score based on opens, clicks, replies
- [ ] Behavioral segments — "opened X but didn't click", "inactive 30 days"
- [ ] Drip campaigns — time-based sequences (day 1, day 3, day 7)
- [ ] A/B testing — subject + content variants, auto winner selection
- [ ] Predictive churn — identify disengaging contacts early

### Canais & Captura
- [ ] WhatsApp integration — automation step that sends WhatsApp (reuse ERP infra)
- [ ] Capture forms — public landing pages with form builder > contacts + trigger automations
- [ ] Webhook triggers — automations triggered by external webhooks (Typeform, CRM, etc.)
- [ ] SMS step — automation step via Twilio or similar

### Templates & Conteudo
- [ ] Drag-and-drop editor — visual template builder (react-email-editor)
- [ ] Conditional merge tags — `{{#if empresa}}...{{/if}}`
- [ ] Inbox preview — Gmail, Outlook, Apple Mail rendering preview
- [ ] Spam score preview — pre-send analysis against spam filters
- [ ] Template gallery — ready-made templates by category
- [ ] Multi-language templates — variants by contact language

### Deliverability & Compliance
- [ ] Email warmup — gradual domain warm-up with progressive scaling
- [ ] Smart bounce management — soft bounce retry, hard bounce blacklist
- [ ] Global suppression list — shared across NoctusAI products

### Analytics & Insights
- [ ] Engagement heatmap — click heatmap on email body
- [ ] Email reply tracking — detect replies, feed contact timeline
- [ ] Cohort analysis — engagement by signup date, source, tags
- [ ] Revenue attribution — link campaigns to ERP/PF revenue

### Integracao & API
- [ ] Bidirectional sync — real-time contact sync with all NoctusAI products
- [ ] Public REST API — endpoints for Zapier, n8n, Make
- [ ] Embeddable forms — JS snippet for external sites
- [ ] CRM pipeline view — kanban by engagement stage (cold > warm > converted)
