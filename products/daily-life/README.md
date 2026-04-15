# Daily Life

Personal productivity hub for individuals and organizations. Manage tasks, goals, habits, calendar events, notes, and focus sessions — all AI-assisted, all in one place.

Designed for individual users who want to optimize their daily routines, and for corporations that purchase the product for their employees to boost organizational productivity.

## Stack

- **Backend**: FastAPI (port 8005)
- **Frontend**: React + TypeScript + Vite (port 8110)
- **Database**: Supabase (schema: `daily_life`)
- **Tenant key**: `org_id`
- **Auth**: SSO + direct login

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8005 --app-dir products/daily-life/backend

# Frontend
cd products/daily-life/frontend && npm run dev
```

## Key Features

- Task management with priorities, categories, due dates, and status tracking
- Goal setting and habit tracking with daily check-ins
- Calendar/schedule with events, reminders, and categories
- Quick notes with tags, search, and pinning
- Focus sessions (Pomodoro, deep work, free)
- Productivity metrics and performance dashboards
- Team management for corporate accounts
- Full NoctusAI shared stack: SSO, notifications, theme, role hierarchy

## Database Tables

| Table | Purpose |
|-------|---------|
| `tarefas` | Tasks with priorities and status |
| `metas` | Goals and habits |
| `checkins` | Daily habit check-ins |
| `eventos` | Calendar events and appointments |
| `notas` | Quick notes and journal |
| `metricas_produtividade` | Daily productivity snapshots |
| `sessoes_foco` | Focus/Pomodoro sessions |
| `status_pagina` | Feature flags |
| `invitations` | Team invitations |

## API Endpoints

- `GET/POST /api/tasks` — Task CRUD
- `GET/POST /api/goals` — Goals and habits CRUD
- `POST /api/goals/{id}/checkin` — Habit check-ins
- `GET/POST /api/schedule` — Calendar events CRUD
- `GET/POST /api/notes` — Notes CRUD
- `GET/POST /api/team` — Team management
- `GET /api/notificacoes` — Notifications proxy
- `GET /api/health` — Health check

## Related System

A separate standalone CLI productivity system exists outside this repo. It uses the same Supabase project but a different schema (`automation_ai`). This product uses `daily_life`. They are architecturally independent.
