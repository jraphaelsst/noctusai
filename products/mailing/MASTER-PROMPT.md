# Mailing — MASTER-PROMPT

> Authoritative development guide for the NoctusAI Mailing product.

## Purpose

Email marketing and automation platform. Helps organizations engage leads and clients through mass email campaigns, automated follow-up sequences, and tracked communications.

## Architecture

**Born from the seed framework.** Backend uses `create_product_app()` from `noctusai_seed`. Frontend will use `createProductApp()` from `@noctusai/seed`. All structural infrastructure (auth, team, notifications, health, layout, routing) is inherited — this product only contains domain code.

### Backend

```
products/mailing/backend/app/
  main.py              → create_product_app() with domain routers
  config.py            → MailingSettings(ProductSettings) + Resend/scheduler config
  database.py          → create_database_module(settings, "mailing")
  dependencies.py      → create_dependencies(db)
  rate_limit.py        → create_product_limiter(settings)
  scheduler.py         → APScheduler (send loop, automation processing, scheduled campaigns)
  routers/
    contacts.py        → CRUD, import CSV, sync, search/filter
    lists.py           → Static lists + dynamic segments
    templates.py       → CRUD, preview, send test
    campaigns.py       → Create, schedule, send, pause, cancel, stats
    automations.py     → CRUD, steps, reorder, activate/pause, enroll
    analytics.py       → Dashboard metrics, campaign stats, automation funnel
    webhooks.py        → Resend event receiver (no auth)
    unsubscribe.py     → Public unsubscribe (no auth, HMAC token)
    settings.py        → Domain verification, sender config
  services/
    contact_service.py
    list_service.py
    template_service.py
    campaign_service.py
    send_service.py        → Core engine: Resend Batch API, template rendering
    automation_service.py
    analytics_service.py
    webhook_service.py
    import_service.py
    sync_service.py
    unsubscribe_service.py
  schemas/
    contacts.py, lists.py, templates.py, campaigns.py, automations.py, analytics.py
```

### Frontend

```
products/mailing/frontend/src/
  App.tsx              → createProductApp() from seed framework
  pages/               → Dashboard, Contacts, Templates, Campaigns, Automations, Analytics, Settings
  components/          → Domain components (ContactTable, CampaignStats, StepBuilder, etc.)
  hooks/               → TanStack Query hooks (useContacts, useCampaigns, useAutomations, etc.)
```

### Database Schema: `mailing`

14 tables: contacts, contact_lists, contact_list_members, templates, campaigns, automations, automation_steps, automation_enrollments, send_logs, link_clicks, unsubscribes, sender_domains, status_pagina, invitations.

## Key Domain Logic

### Send Engine
1. `POST /campaigns/{id}/send` → resolve list → create send_logs (queued) → return immediately
2. APScheduler (30s interval) → pick 100 queued → render templates → Resend Batch API → update status
3. Resend webhooks → update send_logs (delivered, opened, clicked, bounced)

### Automations
- Trigger types: contact_added, tag_added, list_joined, manual, webhook
- Step types: send_email, wait, condition, add_tag, remove_tag, webhook
- Processing: APScheduler (5min interval) → check enrollments with next_action_at <= now()

### Compliance
- Every email includes unsubscribe link (HMAC token)
- List-Unsubscribe header (RFC 8058)
- Bounced/complained contacts auto-excluded from future sends

## Dependencies

- **Resend** — email sending (Batch API + webhooks)
- **APScheduler** — campaign send loop + automation processing
- **Seed framework** — all structural infrastructure
- **`noctusai_lib.llm`** — AI wrappers (see below)

## AI Features (ai-expansion Phases 14 + 8)

Six AI features split across two services. See `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md § Mailing AI Wrappers` for the authoritative tables.

**Phase 14 (2026-04-24)** — five `chat_completion` wrappers in `app/services/ai_service.py`:

| Code | Service fn | Purpose |
|---|---|---|
| M1 | `generate_subjects` | 3–5 subject-line variants with tone |
| M2 | `draft_template` | Responsive HTML body from prompt |
| M5 | `reengagement_variants` | 3 re-engagement email tones |
| M6 | `review_deliverability` | Spam / deliverability findings list |
| M7 | `translate_template` | PT → EN/ES/FR preserving HTML + `{{placeholders}}` |

**Phase 8 (2026-04-25)** — persisted P1 indicator in `app/services/segmentation_service.py`:

| Code | Service fn | Purpose |
|---|---|---|
| M3 | `segment_contacts` | embed → greedy cosine cluster → LLM-name → persist N `<AIIndicator/>` rows to `mailing.ai_outputs` |

**Phase 12 (2026-04-25)** — fourth platform-wide P3 digest adopter in `app/services/campaign_debrief_service.py`:

| Code | Service fn | Purpose |
|---|---|---|
| M4 | `build_debrief` / `send_campaign_debrief` | aggregate `send_logs` + `link_clicks` → LLM 3-paragraph PT debrief → render html/text → fan-out via `noctusai_lib.email.digest.send_digest`. **Auto-fired by `send_service._finalize_campaign_if_done` when the last queued `send_log` drains** (atomic `.neq('status','enviada')` flip is the idempotency boundary). Endpoints: `GET /api/ai/campaigns/{id}/debrief` (preview, no send) + `POST /api/ai/campaigns/{id}/debrief/send {recipient}` (manual re-run path). |

Frontend hooks in `src/hooks/useAI.ts`: `useGenerateSubjects`, `useDraftTemplate`, `useReengagementVariants`, `useDeliverabilityReview`, `useTranslateTemplate`, **`useSegmentContacts`**. M3 is wired with `<AIIndicator refType="contact" refId={c.id} hideIcon/>` in the email cell + a "Segmentar" trigger button in the `Contacts.tsx` header. Standard router opt-in: `standard_routers=["health", "notificacoes", "team", "ai_outputs"]`. Migration: `002_ai_outputs.sql`.

Per-page UI integration for M1/M2/M5/M6/M7 (buttons in campaign / template editors) is follow-up polish — hooks are consumable today; pages can mount buttons when convenient.

## Testing

```bash
cd products/mailing/backend && pytest
```

Implementation checklist: see `TODO-MAILING.md` at repo root.
