# Daily Life Backend

Personal productivity hub. Schema: `daily_life`. Backend port: 8005. Frontend port: 8110.

## Routers (6)

| Router | Prefix | Endpoints | Purpose |
|--------|--------|-----------|---------|
| `health` | `/api/health` | 1 | Service health check |
| `tasks` | `/api/tasks` | 6 | Task CRUD + stats |
| `goals` | `/api/goals` | 5 + 2 checkin | Goals/habits CRUD + check-ins |
| `schedule` | `/api/schedule` | 5 | Calendar events CRUD |
| `notes` | `/api/notes` | 5 | Notes CRUD with search |
| `team` | `/api/team` | 7 | Team/invitation management |
| `notificacoes` | `/api/notificacoes` | 4 | Notification proxy to core |

## Database Tables (14)

| Table | RLS | Tenant | Key Columns |
|-------|-----|--------|-------------|
| `tarefas` | user_id | org_id | titulo, prioridade (alta/media/baixa), status (pendente/em_progresso/concluida/cancelada), data_vencimento |
| `metas` | user_id | org_id | titulo, tipo (meta/habito), frequencia (diario/semanal/mensal), meta_valor, valor_atual, status |
| `checkins` | user_id | — | meta_id, data, valor, nota. UNIQUE(meta_id, data) |
| `eventos` | user_id | org_id | titulo, data_inicio, data_fim, dia_inteiro, local, lembrete_minutos, cor, status |
| `notas` | user_id | org_id | titulo, conteudo, tags (TEXT[]), fixada, categoria |
| `metricas_produtividade` | user_id | — | data, tarefas_concluidas, checkins_realizados, score_produtividade. UNIQUE(user_id, data) |
| `sessoes_foco` | user_id | — | tarefa_id (nullable FK), tipo (pomodoro/deep_work/livre), duracao_minutos, inicio, fim |
| `status_pagina` | public SELECT | — | nome_pagina, status (producao/desenvolvimento/desativado) |
| `invitations` | org_id | org_id | email, role, token, status, expires_at |

## Triggers

- `set_updated_at()` — auto-updates `updated_at` on tarefas, metas, eventos, notas

### Command Knowledge Tables (CLI learning system)

| Table | RLS | Purpose |
|-------|-----|---------|
| `commands` | service_role write, auth read | Known CLI commands (trigger, type, handler) |
| `intent_patterns` | service_role write, auth read | Regex/keyword patterns for Tier 2 matching |
| `context_rules` | user_id | Personal knowledge (contacts, defaults, preferences) |
| `command_history` | user_id | Every CLI interaction logged (tier, success, tokens, time) |
| `learned_promotions` | user_id | LLM interactions auto-promoted to patterns after 3 occurrences |

## Key Patterns

- All data tables are **user-scoped** via `user_id = (SELECT auth.uid())` RLS policies
- Full CRUD policies (SELECT, INSERT, UPDATE, DELETE) per user
- Habit check-ins have a UNIQUE constraint on (meta_id, data) — one check-in per habit per day
- Focus sessions optionally link to a task via `tarefa_id` FK (SET NULL on delete)
- Productivity metrics are daily snapshots with UNIQUE(user_id, data)

## Dual Development Track

This product has a parallel standalone agent system (see `daily.md`). Both share the same schema. The agent system uses the `agno` library for terminal-based AI automation with a three-tier command resolution engine: direct commands (free) -> pattern matching (free) -> LLM reasoning via agno (costs tokens). The `learned_promotions` table powers a self-learning loop that promotes repeated LLM interactions to patterns after 3 successful occurrences. Future convergence planned.
