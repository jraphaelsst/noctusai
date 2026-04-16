# NoctusAI Mailing

Email Marketing & Automation platform for engaging leads and clients.

## Stack

- **Backend**: FastAPI + Supabase (schema: `mailing`, port: 8006)
- **Frontend**: React + TypeScript + Vite (port: 8120)
- **Inherited from seed**: auth, roles, team management, notifications, health check, layout, routing
- **Domain-specific**: contacts, lists, templates, campaigns, automations, analytics

## Features

- Mass email campaigns via Resend Batch API
- Multi-step automation sequences (follow-ups, triggers, conditions)
- Contact management with import (CSV), tags, segments
- HTML email templates with variable interpolation
- Campaign scheduling and live send tracking
- Resend webhook integration (open, click, bounce, complaint)
- Unsubscribe management (LGPD/CAN-SPAM compliant)
- Custom domain verification for sending
- Analytics dashboard (open rate, click rate, bounces, growth)

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8006 --app-dir products/mailing/backend

# Frontend
cd products/mailing/frontend && npm run dev
```

## Tests

```bash
cd products/mailing/backend && pytest
```
