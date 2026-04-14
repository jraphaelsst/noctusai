# Daily Life CLI — Complete Implementation Prompt

> Send this entire file to the agent building the CLI system.
> It contains architecture, database schema, command catalog, and implementation checklist.
> Everything was deliberated and is intentional.

---

## What You're Building

A **terminal-based personal productivity CLI** at `/Users/rapha/Documents/Daily Life/`. Python-powered, AI-augmented, with three processing tiers:

- **Tier 1 — Direct commands** (dictionary lookup, instant, free): `list tasks`, `show today`
- **Tier 2 — Pattern matching** (regex/keyword extraction, instant, free): `add task review PR by friday high priority`
- **Tier 3 — AI reasoning** (agno + LLM, slower, costs tokens): `what should I prioritize today based on my deadlines?`

The system tries Tier 1 first, then 2, then 3. Goal: ~90% of interactions handled without LLM.

## Relationship to NoctusAI Platform

This CLI shares the **same Supabase database schema** (`daily_life`) with the NoctusAI web product at `products/daily-life/`. The web product has:
- 9 backend routers (tasks, goals, schedule, notes, focus, metrics, team, notifications, health)
- Full React frontend with 8 pages
- 207 automated tests

The CLI is a **companion tool** — same data, different interface. Both read/write to the same tables. The CLI adds AI agents, command knowledge system, and terminal UX that the web product doesn't have.

## Tech Stack

- **Python 3.11+**
- **agno** (https://github.com/agno-agi/agno) — agent framework for Tier 3. No substitutes.
- **supabase-py** — database client (service_role key for personal tool)
- **rich** — terminal UI (tables, panels, colors)
- **python-dotenv** — env config
- **Resend or Gmail API** — email (optional)
- **Google Calendar API** — calendar sync (optional)
- **WAHA or Twilio** — WhatsApp (optional)

## Project Structure

```
/Users/rapha/Documents/Daily Life/
├── main.py                       # Entry point
├── requirements.txt
├── .env / .env.example
├── MASTER-PROMPT.md              # This file, persisted
├── COMMANDS.md                   # Generated from command catalog below
├── cli/
│   ├── app.py                    # Main loop: input → resolve → execute → display
│   ├── resolver.py               # Three-tier: direct → pattern → agno
│   ├── display.py                # Rich terminal formatting
│   └── history.py                # Logs to command_history table
├── commands/
│   ├── registry.py               # Loads from DB + code, builds lookup maps
│   ├── tasks_cmd.py              # Task CRUD handlers
│   ├── habits_cmd.py             # Goal/habit handlers
│   ├── schedule_cmd.py           # Calendar handlers
│   ├── notes_cmd.py              # Notes handlers
│   ├── briefing_cmd.py           # Daily/weekly briefing
│   └── system_cmd.py             # help, stats, history, config
├── patterns/
│   ├── parser.py                 # Regex + keyword extraction
│   └── definitions.py            # Loaded from DB + code
├── agents/
│   ├── orchestrator.py           # agno Team router
│   ├── task_agent.py             # Prioritization, reorganization
│   ├── habit_agent.py            # Streak analysis, suggestions
│   ├── calendar_agent.py         # Schedule optimization
│   ├── email_agent.py            # Draft/send emails
│   ├── message_agent.py          # WhatsApp messaging
│   ├── briefing_agent.py         # Intelligent summaries
│   └── notes_agent.py            # Search, summarization
├── tools/
│   ├── supabase_tools.py         # All Supabase CRUD
│   ├── email_tools.py            # Resend/Gmail wrapper
│   ├── calendar_tools.py         # Google Calendar wrapper
│   └── whatsapp_tools.py         # WAHA/Twilio wrapper
├── knowledge/
│   ├── loader.py                 # Loads commands, patterns, context from Supabase
│   ├── context.py                # Contact resolution, defaults, preferences
│   └── learner.py                # Promotes LLM interactions to patterns
├── config/
│   └── settings.py               # Pydantic settings from .env
└── db/
    └── migration.sql             # Reference schema (applied via NoctusAI platform)
```

## Database Schema

The `daily_life` schema is **already created** on the NoctusAI Supabase project (`nyplttplcoyiiqjrvtiw`). All tables exist with RLS enabled.

### Data Tables (shared with web product)

| Table | Key Fields | Purpose |
|-------|-----------|---------|
| `tarefas` | titulo, prioridade (alta/media/baixa), prioridade_ordem, categoria, data_vencimento, status | Tasks |
| `metas` | titulo, tipo (meta/habito), frequencia (diario/semanal/mensal), meta_valor, valor_atual, status | Goals & habits |
| `checkins` | meta_id, data, valor, nota. UNIQUE(meta_id, data) | Habit check-ins |
| `eventos` | titulo, data_inicio, data_fim, dia_inteiro, local, lembrete_minutos, cor, recorrencia, recorrencia_fim | Calendar |
| `notas` | titulo, conteudo, tags TEXT[], fixada, categoria | Notes |
| `sessoes_foco` | tipo (pomodoro/deep_work/livre), duracao_minutos, tarefa_id, inicio, fim | Focus sessions |
| `metricas_produtividade` | data, tarefas_concluidas/criadas, checkins, score. UNIQUE(user_id, data) | Daily metrics |

### CLI-Specific Tables (command knowledge system)

| Table | Key Fields | Purpose |
|-------|-----------|---------|
| `commands` | trigger, type (exact/pattern/alias), handler, parameters, category, examples | Known commands |
| `intent_patterns` | pattern, pattern_type (regex/keyword/fuzzy), mapped_command_id, handler, confidence_threshold | Pattern matching |
| `context_rules` | user_id, rule_type (contact/location/default/alias/preference), key, value JSONB | Personal context |
| `command_history` | raw_input, resolved_command, tier_used (direct/pattern/llm/failed), tokens_used, execution_time_ms | Every interaction |
| `learned_promotions` | raw_input, extracted_intent, extracted_handler, status (pending/approved/rejected/auto_approved), occurrences | Learning engine |

All tables have `user_id` + RLS policies using `(SELECT auth.uid())`.

## Command Catalog

### Tasks

**Direct (exact match):**

| Trigger | Handler | Description |
|---------|---------|-------------|
| `list tasks` | `tasks_cmd.list_all` | Pending tasks |
| `list all tasks` | `tasks_cmd.list_all_statuses` | All statuses |
| `tasks today` | `tasks_cmd.due_today` | Due today |
| `tasks overdue` | `tasks_cmd.overdue` | Past due date |
| `tasks high` | `tasks_cmd.by_priority("alta")` | High priority |
| `task stats` | `tasks_cmd.stats` | Count by status |

**Pattern (regex/keyword):**

| Pattern | Handler | Examples |
|---------|---------|----------|
| `add task {title}` | `tasks_cmd.create` | "add task review PR" |
| `add task {title}, {priority} priority` | `tasks_cmd.create` | "add task fix bug, high priority" |
| `add task {title} by {date}` | `tasks_cmd.create` | "add task send report by friday" |
| `add task {title} by {date}, {priority}` | `tasks_cmd.create` | "add task demo prep by thursday, high" |
| `add task {title} [{category}]` | `tasks_cmd.create` | "add task review PR [work]" |
| `complete task {id_or_title}` | `tasks_cmd.complete` | "complete task 3" |
| `delete task {id_or_title}` | `tasks_cmd.delete` | "delete task 5" |
| `start task {id_or_title}` | `tasks_cmd.start` | "start task demo prep" |
| `cancel task {id_or_title}` | `tasks_cmd.cancel` | "cancel task old report" |

**Aliases:** `lt`→list tasks, `at`→add task, `ct`→complete task, `dt`→delete task

### Goals & Habits

**Direct:**

| Trigger | Handler |
|---------|---------|
| `list goals` | `habits_cmd.list_goals` |
| `list habits` | `habits_cmd.list_habits` |
| `habit streaks` | `habits_cmd.streaks` |
| `habits today` | `habits_cmd.today_status` |

**Pattern:**

| Pattern | Handler | Examples |
|---------|---------|----------|
| `add goal {title}` | `habits_cmd.create_goal` | "add goal run a marathon" |
| `add goal {title} by {date}` | `habits_cmd.create_goal` | "add goal lose 5kg by june" |
| `add habit {title}` | `habits_cmd.create_habit` | "add habit meditate" |
| `add habit {title} {frequency}` | `habits_cmd.create_habit` | "add habit gym weekly" |
| `check in {habit}` | `habits_cmd.checkin` | "check in gym" |
| `done with {habit}` | `habits_cmd.checkin` | "done with meditation" |

**Aliases:** `lh`→list habits, `lg`→list goals, `ci`→check in

### Schedule

**Direct:**

| Trigger | Handler |
|---------|---------|
| `show today` / `today` | `schedule_cmd.today` |
| `show tomorrow` / `tomorrow` | `schedule_cmd.tomorrow` |
| `show week` / `week` | `schedule_cmd.this_week` |
| `list events` / `cal` | `schedule_cmd.list_all` |

**Pattern:**

| Pattern | Handler | Examples |
|---------|---------|----------|
| `schedule {title} {date} at {time}` | `schedule_cmd.create` | "schedule dentist friday at 3pm" |
| `schedule {title} tomorrow at {time}` | `schedule_cmd.create` | "schedule call tomorrow at 10am" |
| `cancel event {id_or_title}` | `schedule_cmd.cancel` | "cancel event dentist" |
| `move event {id_or_title} to {date}` | `schedule_cmd.reschedule` | "move dentist to next monday" |

### Notes

**Direct:**

| Trigger | Handler |
|---------|---------|
| `list notes` / `ln` | `notes_cmd.list_recent` |
| `pinned notes` | `notes_cmd.list_pinned` |

**Pattern:**

| Pattern | Handler | Examples |
|---------|---------|----------|
| `note {title}: {content}` | `notes_cmd.create` | "note meeting: discussed Q3 roadmap" |
| `note {content}` | `notes_cmd.quick_create` | "note remember to call dentist" |
| `search notes {query}` | `notes_cmd.search` | "search notes roadmap" |
| `pin note {id_or_title}` | `notes_cmd.pin` | "pin note meeting" |

### Briefings & System

| Trigger | Handler |
|---------|---------|
| `briefing` / `daily` | `briefing_cmd.daily` |
| `weekly` | `briefing_cmd.weekly` |
| `score` | `briefing_cmd.productivity_score` |
| `help` | `system_cmd.help` |
| `history` | `system_cmd.recent_history` |
| `integrations` | `system_cmd.integration_status` |
| `exit` / `quit` | `system_cmd.exit` |

### AI-Only (always Tier 3)

| Intent | Agent |
|--------|-------|
| "what should I prioritize today?" | task_agent |
| "help me reorganize my tasks" | task_agent |
| "summarize my week" | briefing_agent |
| "am I on track with my goals?" | habit_agent |
| "find a time for a 1-hour meeting this week" | calendar_agent |
| "draft an email to {person} about {topic}" | email_agent |

### Parsing Rules

**Dates:** today, tomorrow, monday-sunday (next occurrence), next monday, april 20, 20/04, in 3 days, next week, end of month.

**Priorities:** high/alta/urgent/! → alta, medium/media/normal → media, low/baixa/minor → baixa.

### Context Rules (seed data for `context_rules`)

| Type | Key | Value |
|------|-----|-------|
| default | priority | "media" |
| default | habit_frequency | "diario" |
| default | event_duration | 60 |
| default | reminder_minutes | 30 |
| preference | date_format | "pt-BR" |
| preference | week_start | "monday" |

## Learner Engine (self-improvement loop)

After every successful Tier 3 interaction:

1. Extract structured metadata from the LLM response: `{ intent, handler, parameters, suggested_pattern, confidence }`
2. Check `learned_promotions` for similar intents. If exists: increment `occurrences`. If not: create pending.
3. **Auto-promote at 3 occurrences** — creates `intent_patterns` row, marks as `auto_approved`. Next time, Tier 2 catches it.
4. Manual review via CLI: `learner status`, `learner approve {id}`, `learner reject {id}`

```
User types something → Tier 1 miss → Tier 2 miss → Tier 3 (LLM) handles it
  → learner extracts pattern → stores in learned_promotions (occurrences=1)
User types similar → same flow → occurrences=2
User types again → same flow → occurrences=3 → AUTO-PROMOTE to intent_patterns
User types fourth time → Tier 2 MATCHES → handled directly, free, learned
```

## Rules

- **Write real code.** Every handler, agent, tool must be functional Python.
- **Use agno properly.** Read their docs. Agent + Tool + Team APIs.
- **Use Supabase service_role key** — this is a personal tool.
- **Tier 1 first.** Get direct commands working before patterns. Patterns before agno.
- **No web server.** Terminal only. No FastAPI/Flask.
- **Seed knowledge tables** on first run from the command catalog above.
- **Log everything to command_history.** Tier used, success, duration, tokens.
- **Portuguese for data fields** (titulo, descricao, prioridade). **English for code.**
- **Rich terminal output.** Tables, panels, colored text.
- **Handle missing credentials gracefully.** No Gmail key → email agent says so and skips.
- **Architecture for future SaaS.** Agents decoupled from CLI. Tools decoupled from agents.

---

## Implementation Checklist

### Phase 1: Scaffold + Supabase Connection
- [ ] Create project directory at `/Users/rapha/Documents/Daily Life/`
- [ ] Create `requirements.txt` (agno, supabase, rich, python-dotenv, pydantic-settings)
- [ ] Create `.env.example` with placeholder keys
- [ ] Create `config/settings.py` — Pydantic settings from .env
- [ ] Create `tools/supabase_tools.py` — CRUD for all tables (use service_role key)
- [ ] Test: connect to Supabase, read `daily_life.tarefas` → works
- [ ] Create `db/migration.sql` — reference copy of the schema
- [ ] Save this file as `MASTER-PROMPT.md` in the project root

### Phase 2: CLI Framework + Direct Commands (Tier 1)
- [ ] Create `cli/app.py` — main input loop with rich prompt
- [ ] Create `cli/display.py` — rich tables, panels, colors
- [ ] Create `cli/resolver.py` — three-tier resolution (direct → pattern → agno)
- [ ] Create `cli/history.py` — logs to `command_history`
- [ ] Create `commands/registry.py` — loads from DB + hardcoded
- [ ] Create `commands/tasks_cmd.py` — list, add, complete, delete, start, cancel, stats
- [ ] Create `commands/habits_cmd.py` — list goals, list habits, check in, streaks, today status
- [ ] Create `commands/schedule_cmd.py` — today, tomorrow, week, list events, create, cancel, move
- [ ] Create `commands/notes_cmd.py` — list, create, search, pin, delete
- [ ] Create `commands/briefing_cmd.py` — daily and weekly briefings from data
- [ ] Create `commands/system_cmd.py` — help, history, stats, version, config, integrations, exit
- [ ] Seed `commands` table with all exact commands from catalog
- [ ] Seed `intent_patterns` table with initial patterns
- [ ] Test: `list tasks` → formatted table, no LLM, < 50ms
- [ ] Test: `briefing` → compiled from tasks + events + habits
- [ ] Test: `help` → shows all categories and commands

### Phase 3: Pattern Matching (Tier 2)
- [ ] Create `patterns/parser.py` — regex + keyword extraction
- [ ] Create `patterns/definitions.py` — loads patterns from DB, matches input
- [ ] Implement date parsing (today, tomorrow, friday, next week, april 20, in 3 days)
- [ ] Implement priority parsing (high → alta, low → baixa)
- [ ] Wire resolver: Tier 1 miss → try Tier 2 → extract params → call handler
- [ ] Test: `add task review PR by friday high` → creates task with parsed fields, no LLM
- [ ] Test: `schedule dentist friday at 3pm` → creates event
- [ ] Test: `check in gym` → records check-in
- [ ] Test: `note meeting: discussed Q3 roadmap` → creates note

### Phase 4: AI Reasoning (Tier 3 — agno)
- [ ] Read agno docs: understand Agent, Tool, Team APIs
- [ ] Create `agents/task_agent.py` — prioritize, reorganize, suggest
- [ ] Create `agents/briefing_agent.py` — intelligent summaries with recommendations
- [ ] Create `agents/orchestrator.py` — agno Team that routes to the right agent
- [ ] Wire resolver: Tier 1+2 miss → send to agno Team
- [ ] Test: `what should I prioritize today?` → agent reasons over data
- [ ] Create `agents/email_agent.py` — draft and send emails
- [ ] Create `agents/calendar_agent.py` — schedule optimization, conflict resolution
- [ ] Create `agents/message_agent.py` — WhatsApp messaging
- [ ] Create `agents/habit_agent.py` — streak analysis, suggestions
- [ ] Create `agents/notes_agent.py` — search, summarization, linking

### Phase 5: Knowledge System + Learning
- [ ] Create `knowledge/loader.py` — loads commands, patterns, context from Supabase on startup
- [ ] Create `knowledge/context.py` — resolves "John" → contact, defaults, preferences
- [ ] Create `knowledge/learner.py` — automatic promotion engine
- [ ] Implement auto-promotion at 3 occurrences threshold
- [ ] Seed `context_rules` with defaults and preferences
- [ ] Test: successful LLM interaction → stored in learned_promotions
- [ ] Test: 3 similar interactions → auto-promoted to intent_patterns
- [ ] Test: 4th interaction → caught by Tier 2, no LLM

### Phase 6: External Integrations + Polish
- [ ] Wire Resend/Gmail for email sending (skip gracefully if no API key)
- [ ] Wire Google Calendar API for sync (skip gracefully if no key)
- [ ] Wire WAHA/Twilio for WhatsApp (skip gracefully if no key)
- [ ] Add rich progress bars for long operations
- [ ] Add error handling for all edge cases
- [ ] Write `README.md` with setup and usage guide
- [ ] Generate `COMMANDS.md` from the command catalog above
- [ ] Final test: full interactive session exercising all tiers

### Verification Milestones

After Phase 2:
```
$ python main.py
Daily Life v0.1

> list tasks
┌────────────────────────┬──────────┬────────────┬──────────┐
│ Titulo                 │ Prioridade│ Vencimento │ Status   │
├────────────────────────┼──────────┼────────────┼──────────┤
│ Review quarterly report│ alta     │ 2026-04-20 │ pendente │
└────────────────────────┴──────────┴────────────┴──────────┘
[direct] 1 task — 12ms
```

After Phase 4:
```
> I have too many tasks, help me reprioritize
[llm] Analyzing 12 tasks...

Based on your deadlines:
  DROP: "reorganize shared drive" — no deadline, low impact
  DEFER: "update documentation" — move to next week
  FOCUS: "client demo prep" — Thursday deadline, high visibility

Want me to apply? (y/n)
[llm] 847 tokens — 2.3s
```

After Phase 5:
```
> (fourth time typing a similar request)
[pattern] Matched learned pattern — 3ms (was LLM at 2.3s)
```
