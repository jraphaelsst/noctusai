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
| Metrics | `metricas_produtividade` | `/api/metrics` | Daily productivity snapshots and scoring |
| Team | `invitations` | `/api/team` | Organization member management |
| AI weekly review | (read-only over tasks/metas/checkins/notas/sessoes_foco) | `/api/ai/weekly-review` (GET) | Phase 11 D6 Friday review. `weekly_review_service.py` aggregates past 7 days, asks LLM for 3-paragraph PT narrative (`cache=False` — LGPD). |
| AI today's brief | (read-only over today's tarefas/eventos/checkins) | `/api/ai/daily-brief` (GET) | Phase 13 D1 today's brief badge. `daily_brief_service.py` builds `{chip ≤32 chars, summary ≤200 chars}` from today's data. Frontend `<DailyBriefBadge>` mounted via `LayoutEnrichment.aiBadge` (P4 pattern). Hook `useDailyBrief()` (15-min staleTime). `cache=False` — LGPD. **2026-04-27**: panel mounts `<AIFeedbackButtons output_ref="digest:dl-daily-brief:<YYYY-MM-DD>" size="sm"/>` at the bottom (`digest-feedback-mount` project). |

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
- **`noctusai_lib.llm`** — for the D4 note-to-task extraction (see below)

## AI Features (ai-expansion Phase 16, 2026-04-24)

| Code | Service fn | Endpoint | Hook | Notes |
|---|---|---|---|---|
| **D4** | `extract_tasks_from_note(note_content, org_id?)` | `POST /api/notes/{note_id}/extract-tasks` | `useExtractTasksFromNote()` | `cache=False` (personal content); caps at 10 tasks; never auto-creates tasks — UI confirms each. |

Future AI features for Daily Life (e.g. D1 daily brief, D2 goal decomposition, D3 schedule optimizer, D6 weekly review) land in subsequent phases per `projects/ai-expansion/PROJECT.md` — they will live alongside `extract_tasks_from_note` in this same `ai_service.py` module.

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
