# Daily Life — Master Prompt

## Purpose

Personal productivity hub within the NoctusAI platform. Serves two audiences:
1. **Individual users** — optimize daily routines, track habits, manage tasks and goals
2. **Corporate accounts** — organizations purchase access for employees to boost team productivity

AI-first design: every feature should be buildable with AI assistance and eventually automatable via AI agents.

## Architecture

- **Schema**: `daily_life`
- **Backend port**: 8005 | **Frontend port**: 8110
- **Tenant key**: `org_id`
- **Auth**: SSO + direct login (follows NoctusAI shared auth pattern)
- **Pattern**: `routers/ -> services/ -> schemas/` + `dependencies.py`, `database.py`

## Key Domains

| Domain | Table | Router | Description |
|--------|-------|--------|-------------|
| Tasks | `tarefas` | `/api/tasks` | Task management with priorities, categories, due dates |
| Goals | `metas` | `/api/goals` | Goals (one-time targets) and habits (recurring tracking) |
| Check-ins | `checkins` | `/api/goals/{id}/checkin` | Daily habit completions |
| Schedule | `eventos` | `/api/schedule` | Calendar events with reminders, locations, colors |
| Notes | `notas` | `/api/notes` | Quick notes with tags, search, pinning |
| Focus | `sessoes_foco` | `/api/foco` | Pomodoro / deep work sessions linked to tasks |
| Metrics | `metricas_produtividade` | `/api/metricas` | Daily productivity snapshots and scoring |
| Team | `invitations` | `/api/team` | Organization member management |

## Development Guidelines

- Follow shared patterns from `noctusai_lib` — auth, invitations, notifications, responses
- Router -> Service pattern: business logic in services, routers are thin
- RLS policies use `(SELECT auth.uid())` pattern — all tables are user-scoped
- Portuguese for business domain (`tarefas`, `metas`, `notas`), English for technical
- N+1 zero tolerance: batch reads with `.in_()`, batch writes with `.insert(rows)`
- Mobile-first responsive design: test at 375/768/1440px
- Toasts via `sonner` only
- TanStack Query for server state, Zustand for UI state

## Pages and Status

| Page | Route | Status |
|------|-------|--------|
| Dashboard | `/` | producao |
| Tarefas | `/tarefas` | producao |
| Metas | `/metas` | producao |
| Agenda | `/agenda` | producao |
| Notas | `/notas` | producao |
| Foco | `/foco` | desenvolvimento |
| Metricas | `/metricas` | desenvolvimento |
| Equipe | `/equipe` | producao |

## Testing

```bash
cd products/daily-life/backend && pytest
```

## Dependencies

- **Shared backend**: `noctusai_lib` (auth, roles, invitations, email_templates, notifications, page_status, responses, exceptions, middleware, app_factory, database, config, testing)
- **Shared frontend**: `@noctusai/lib` (api, sso, roles, page-status, auth, stores, hooks, notifications, supabase, components)
- **Design system**: `@noctusai/lib/design-system` (AppShell, Sidebar, Header, LoginForm, etc.)

## Related System

A separate standalone CLI productivity system exists outside this repo (`/Users/rapha/Documents/Daily Life/`). It uses the same Supabase project but a different schema (`automation_ai`). This product uses `daily_life` schema. They are architecturally independent — do not read or write across schemas.

## Roadmap (MVP)

1. Wire up task CRUD UI (list, create, edit, delete, status changes)
2. Wire up goals/habits UI with check-in tracking
3. Wire up calendar view with event management
4. Wire up notes UI with search and pinning
5. Build focus session timer (Pomodoro/deep work)
6. Build daily productivity metrics dashboard
7. Add AI-assisted task suggestions and prioritization
8. Add automation hooks for external integrations (email, calendar sync)
